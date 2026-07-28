from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from trade_execution_safety_lab.engine import ExecutionPolicy
from trade_execution_safety_lab.models import ReceiptOutcome
from trade_execution_safety_lab.receipts import (
    AtomicReceiptStore,
    OUTPUT_SENTINEL,
    prepare_output_directory,
    verify_receipt_payload,
    write_json_artifact,
    write_text_artifact,
)
from trade_execution_safety_lab.restart import RestartAction, inspect_restart
from trade_execution_safety_lab.simulator import (
    SimulatedOrderPlan,
    SimulatedVenue,
    SimulationStep,
)

from tests.helpers import StoreTestCase, make_intent


class OutputSafetyTests(unittest.TestCase):
    def test_broad_current_directory_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            prepare_output_directory(Path.cwd(), reset=False)

    def test_home_directory_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            prepare_output_directory(Path.home(), reset=False)

    def test_reset_requires_lab_sentinel_for_nonempty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "other-output"
            output.mkdir()
            (output / "unrelated.txt").write_text("preserve me", encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare_output_directory(output, reset=True)
            self.assertTrue((output / "unrelated.txt").exists())

    def test_lab_owned_directory_can_be_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = prepare_output_directory(Path(temporary) / "output", reset=False)
            (output / "old.txt").write_text("old", encoding="utf-8")
            output = prepare_output_directory(output, reset=True)
            self.assertTrue((output / OUTPUT_SENTINEL).is_file())
            self.assertFalse((output / "old.txt").exists())

    def test_nonempty_output_requires_explicit_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = prepare_output_directory(Path(temporary) / "output", reset=False)
            with self.assertRaises(FileExistsError):
                prepare_output_directory(output, reset=False)

    def test_symlink_output_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            target.mkdir()
            link = base / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                prepare_output_directory(link, reset=False)

    def test_receipt_store_must_be_inside_prepared_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                AtomicReceiptStore(Path(temporary) / "receipts")

    def test_artifact_names_cannot_escape_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                write_json_artifact(root, "../summary.json", {})
            with self.assertRaises(ValueError):
                write_text_artifact(root, "nested/summary.md", "text")


class ReceiptAndRestartTests(StoreTestCase):
    def _filled_receipt(self):
        engine, venue = self.make_engine(
            plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "25"),)
            ),
            policy=ExecutionPolicy(maximum_order_polls=1),
        )
        receipt = engine.execute(make_intent(), scenario="test-full-fill")
        self.assertEqual(receipt.outcome, ReceiptOutcome.FILLED)
        return receipt, venue

    def test_stored_receipt_verifies(self) -> None:
        receipt, _ = self._filled_receipt()
        payload = self.store.read_verified(receipt.intent.client_order_id)
        self.assertIsNotNone(payload)
        self.assertTrue(verify_receipt_payload(payload))  # type: ignore[arg-type]

    def test_receipt_file_permissions_are_restrictive(self) -> None:
        receipt, _ = self._filled_receipt()
        path = self.store.root / f"{receipt.intent.client_order_id}.json"
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_tampered_receipt_is_rejected(self) -> None:
        receipt, _ = self._filled_receipt()
        path = self.store.root / f"{receipt.intent.client_order_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["outcome"] = "cancelled"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.read_verified(receipt.intent.client_order_id)

    def test_verified_receipt_suppresses_restart_submission(self) -> None:
        receipt, venue = self._filled_receipt()
        decision = inspect_restart(
            self.store,
            venue,
            receipt.intent.client_order_id,
        )
        self.assertEqual(decision.action, RestartAction.RETURN_VERIFIED_RECEIPT)
        self.assertEqual(decision.receipt_id, receipt.receipt_id)

    def test_existing_venue_order_requires_reconciliation(self) -> None:
        venue = SimulatedVenue()
        intent = make_intent("VENUE-ONLY")
        order = venue.submit(intent)
        decision = inspect_restart(self.store, venue, intent.client_order_id)
        self.assertEqual(decision.action, RestartAction.RECONCILE_EXISTING_ORDER)
        self.assertEqual(decision.venue_order_id, order.venue_order_id)

    def test_absent_receipt_and_order_is_safe_to_submit(self) -> None:
        decision = inspect_restart(self.store, SimulatedVenue(), "NEW-ORDER")
        self.assertEqual(decision.action, RestartAction.SAFE_TO_SUBMIT)

    def test_receipt_payload_declares_offline_boundary(self) -> None:
        receipt, _ = self._filled_receipt()
        payload = receipt.to_dict()
        self.assertEqual(payload["mode"], "offline-simulation")
        self.assertFalse(payload["network_used"])
        self.assertFalse(payload["credentials_required"])
