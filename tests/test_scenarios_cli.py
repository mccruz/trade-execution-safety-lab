from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from trade_execution_safety_lab.cli import main
from trade_execution_safety_lab.receipts import verify_receipt_payload
from trade_execution_safety_lab.scenarios import (
    SCENARIOS,
    run_demo,
    scenario_catalog,
    scenario_names,
)
from trade_execution_safety_lab.toy_signal import alternating_fixture_side
from trade_execution_safety_lab.models import Side


class ScenarioTests(unittest.TestCase):
    def test_catalog_names_are_unique(self) -> None:
        names = scenario_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), len(SCENARIOS))

    def test_catalog_has_plain_language_descriptions(self) -> None:
        for item in scenario_catalog():
            self.assertTrue(item["description"].endswith("."))
            self.assertTrue(item["expected_outcome"])

    def test_complete_demo_passes_without_network_or_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_demo(Path(temporary) / "demo", reset=False)
            self.assertTrue(summary["passed"])
            self.assertFalse(summary["network_used"])
            self.assertFalse(summary["credentials_required"])
            self.assertEqual(summary["scenario_count"], len(SCENARIOS))

    def test_demo_writes_verified_receipts_and_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "demo"
            summary = run_demo(root, reset=False)
            self.assertTrue((root / "summary.json").is_file())
            self.assertTrue((root / "summary.md").is_file())
            for item in summary["scenarios"]:  # type: ignore[union-attr]
                path = root / str(item["receipt"])
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(verify_receipt_payload(payload))

    def test_single_scenario_selection_runs_only_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_demo(
                Path(temporary) / "demo",
                reset=False,
                selected_scenario="cancel-fill-race",
            )
            self.assertEqual(summary["scenario_count"], 1)
            self.assertEqual(
                summary["scenarios"][0]["name"],  # type: ignore[index]
                "cancel-fill-race",
            )

    def test_unknown_scenario_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                run_demo(
                    Path(temporary) / "demo",
                    reset=False,
                    selected_scenario="not-a-scenario",
                )

    def test_restart_evidence_suppresses_duplicate_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_demo(Path(temporary) / "demo", reset=False)
            restart = summary["restart_evidence"]
            self.assertEqual(
                restart["action"],  # type: ignore[index]
                "return-verified-receipt",
            )

    def test_toy_signal_is_deliberately_non_economic(self) -> None:
        self.assertEqual(alternating_fixture_side(0), Side.BUY)
        self.assertEqual(alternating_fixture_side(1), Side.SELL)
        with self.assertRaises(ValueError):
            alternating_fixture_side(-1)


class CliTests(unittest.TestCase):
    def test_list_connectors_is_offline_and_explains_boundaries(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["list-connectors"])
        rendered = output.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("offline-simulator:", rendered)
        self.assertIn("bybit-testnet:", rendered)
        self.assertIn("no live trading", rendered)

    def test_list_scenarios_is_human_readable(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["list-scenarios"])
        self.assertEqual(status, 0)
        self.assertIn("full-fill:", output.getvalue())
        self.assertIn("expected: filled", output.getvalue())

    def test_demo_command_reports_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(
                    [
                        "demo",
                        "--output-dir",
                        str(Path(temporary) / "demo"),
                    ]
                )
            self.assertEqual(status, 0)
            self.assertIn("no network, no credentials", output.getvalue())

    def test_verify_receipt_command_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "demo"
            summary = run_demo(
                root,
                reset=False,
                selected_scenario="full-fill",
            )
            receipt_path = root / summary["scenarios"][0]["receipt"]  # type: ignore[index,operator]
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            payload["outcome"] = "cancelled"
            receipt_path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(["verify-receipt", str(receipt_path)])
            self.assertEqual(status, 1)
            self.assertIn("failed", output.getvalue())

    def test_demo_refuses_overwrite_without_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "demo"
            self.assertEqual(main(["demo", "--output-dir", str(root)]), 0)
            error = io.StringIO()
            with redirect_stderr(error):
                status = main(["demo", "--output-dir", str(root)])
            self.assertEqual(status, 2)
            self.assertIn("not empty", error.getvalue())
