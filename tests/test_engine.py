from __future__ import annotations

from decimal import Decimal
import unittest

from trade_execution_safety_lab.adapters import VenueError, VenueErrorCategory
from trade_execution_safety_lab.engine import ExecutionPolicy
from trade_execution_safety_lab.models import (
    OrderStatus,
    PositionSnapshot,
    ReceiptOutcome,
)
from trade_execution_safety_lab.receipts import verify_receipt_payload
from trade_execution_safety_lab.simulator import (
    SimulatedOrderPlan,
    SimulatedVenue,
    SimulationStep,
)

from tests.helpers import StoreTestCase, make_intent


class PositionFailureVenue(SimulatedVenue):
    def positions(self) -> tuple[PositionSnapshot, ...]:
        raise VenueError(
            "synthetic position failure",
            category=VenueErrorCategory.TRANSIENT,
            retryable=True,
        )


class PostflightFailureVenue(SimulatedVenue):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.position_calls = 0

    def positions(self) -> tuple[PositionSnapshot, ...]:
        self.position_calls += 1
        if self.position_calls > 1:
            raise VenueError(
                "synthetic postflight failure",
                category=VenueErrorCategory.TRANSIENT,
                retryable=True,
            )
        return super().positions()


class CancelFailureVenue(SimulatedVenue):
    def cancel(self, venue_order_id: str):
        raise VenueError(
            "synthetic cancel failure",
            category=VenueErrorCategory.TRANSIENT,
            retryable=True,
        )


class LookupFailureVenue(SimulatedVenue):
    def find_by_client_order_id(self, client_order_id: str):
        raise VenueError(
            "synthetic lookup failure",
            category=VenueErrorCategory.TRANSIENT,
            retryable=True,
        )


class EngineTests(StoreTestCase):
    def test_full_fill_reconciles_and_authorizes_continuation(self) -> None:
        engine, venue = self.make_engine(
            plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "25"),)
            )
        )
        receipt = engine.execute(make_intent(), scenario="full-fill")
        self.assertEqual(receipt.outcome, ReceiptOutcome.FILLED)
        self.assertTrue(receipt.next_action_authorized)
        self.assertEqual(engine.expected_positions["DEMO-USD"], Decimal("2"))
        self.assertEqual(venue.submit_count, 1)

    def test_partial_fill_cancel_defers_but_reconciles_exposure(self) -> None:
        engine, _ = self.make_engine(
            plan=SimulatedOrderPlan(
                poll_steps=(
                    SimulationStep.fill("1", "25"),
                    SimulationStep.no_change(),
                )
            ),
            policy=ExecutionPolicy(maximum_order_polls=2),
        )
        receipt = engine.execute(make_intent(), scenario="partial")
        self.assertEqual(receipt.outcome, ReceiptOutcome.PARTIAL_FILL_DEFERRED)
        self.assertFalse(receipt.next_action_authorized)
        self.assertEqual(engine.expected_positions["DEMO-USD"], Decimal("1"))

    def test_fill_during_cancel_is_not_misclassified_as_cancelled(self) -> None:
        engine, _ = self.make_engine(
            plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.no_change(),),
                cancel_steps=(SimulationStep.fill("2", "25"),),
            ),
            policy=ExecutionPolicy(maximum_order_polls=1),
        )
        receipt = engine.execute(make_intent(), scenario="cancel-race")
        self.assertEqual(receipt.outcome, ReceiptOutcome.FILLED)
        self.assertEqual(receipt.order.status, OrderStatus.FILLED)  # type: ignore[union-attr]

    def test_unresolved_cancel_fails_closed(self) -> None:
        engine, _ = self.make_engine(
            plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.no_change(),),
                cancel_steps=(
                    SimulationStep.no_change(),
                    SimulationStep.no_change(),
                ),
            ),
            policy=ExecutionPolicy(
                maximum_order_polls=1,
                maximum_cancel_polls=1,
            ),
        )
        receipt = engine.execute(make_intent(), scenario="unresolved")
        self.assertEqual(receipt.outcome, ReceiptOutcome.UNKNOWN_DEFERRED)
        self.assertIn("cancel-state-unresolved", receipt.reason_codes)

    def test_validation_block_never_submits(self) -> None:
        engine, venue = self.make_engine()
        receipt = engine.execute(
            make_intent(quantity="0"),
            scenario="invalid",
        )
        self.assertEqual(receipt.outcome, ReceiptOutcome.VALIDATION_BLOCKED)
        self.assertEqual(venue.submit_count, 0)

    def test_position_drift_never_submits(self) -> None:
        venue = SimulatedVenue(
            initial_positions=(
                PositionSnapshot("DEMO-USD", Decimal("3"), Decimal("25"), 1),
            )
        )
        engine, venue = self.make_engine(venue=venue)
        receipt = engine.execute(make_intent(), scenario="drift")
        self.assertEqual(receipt.outcome, ReceiptOutcome.RECONCILIATION_BLOCKED)
        self.assertEqual(venue.submit_count, 0)

    def test_rejected_order_is_not_retried(self) -> None:
        engine, venue = self.make_engine(
            plan=SimulatedOrderPlan(submit_status=OrderStatus.REJECTED)
        )
        receipt = engine.execute(make_intent(), scenario="rejected")
        self.assertEqual(receipt.outcome, ReceiptOutcome.REJECTED)
        self.assertEqual(venue.submit_count, 1)
        self.assertFalse(receipt.next_action_authorized)

    def test_transient_observation_failure_defers(self) -> None:
        engine, _ = self.make_engine(
            plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.disconnect(),)
            )
        )
        receipt = engine.execute(make_intent(), scenario="disconnect")
        self.assertEqual(receipt.outcome, ReceiptOutcome.VENUE_DEFERRED)
        self.assertIn("order-observation-unavailable", receipt.reason_codes)

    def test_submit_failure_is_unconfirmed_and_not_retried(self) -> None:
        engine, venue = self.make_engine(
            plan=SimulatedOrderPlan(
                submit_error_category=VenueErrorCategory.RATE_LIMIT
            )
        )
        receipt = engine.execute(make_intent(), scenario="rate-limit")
        self.assertEqual(receipt.outcome, ReceiptOutcome.VENUE_DEFERRED)
        self.assertEqual(venue.submit_count, 0)
        self.assertIn("submit-unconfirmed", receipt.reason_codes)

    def test_preflight_position_failure_defers_before_submit(self) -> None:
        venue = PositionFailureVenue()
        engine, venue = self.make_engine(venue=venue)
        receipt = engine.execute(make_intent(), scenario="preflight-failure")
        self.assertEqual(receipt.outcome, ReceiptOutcome.VENUE_DEFERRED)
        self.assertEqual(venue.submit_count, 0)

    def test_existing_order_lookup_failure_blocks_submission(self) -> None:
        venue = LookupFailureVenue()
        engine, venue = self.make_engine(venue=venue)
        receipt = engine.execute(make_intent(), scenario="lookup-failure")
        self.assertEqual(receipt.outcome, ReceiptOutcome.VENUE_DEFERRED)
        self.assertIn("existing-order-lookup-unavailable", receipt.reason_codes)
        self.assertEqual(venue.submit_count, 0)

    def test_postflight_position_failure_is_unknown(self) -> None:
        venue = PostflightFailureVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "25"),)
            )
        )
        engine, _ = self.make_engine(venue=venue)
        receipt = engine.execute(make_intent(), scenario="postflight-failure")
        self.assertEqual(receipt.outcome, ReceiptOutcome.UNKNOWN_DEFERRED)
        self.assertFalse(receipt.next_action_authorized)

    def test_cancel_failure_is_unknown(self) -> None:
        venue = CancelFailureVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.no_change(),)
            )
        )
        engine, _ = self.make_engine(
            venue=venue,
            policy=ExecutionPolicy(maximum_order_polls=1),
        )
        receipt = engine.execute(make_intent(), scenario="cancel-failure")
        self.assertEqual(receipt.outcome, ReceiptOutcome.UNKNOWN_DEFERRED)
        self.assertIn("cancel-unconfirmed", receipt.reason_codes)

    def test_existing_order_is_recovered_without_duplicate_submit(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "25"),)
            )
        )
        intent = make_intent()
        venue.submit(intent)
        engine, venue = self.make_engine(venue=venue)
        receipt = engine.execute(intent, scenario="recovered")
        self.assertEqual(receipt.outcome, ReceiptOutcome.FILLED)
        self.assertEqual(venue.submit_count, 1)
        self.assertIn("order.recovered", [event.kind for event in receipt.events])

    def test_repeated_execute_returns_same_receipt(self) -> None:
        engine, venue = self.make_engine(
            plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "25"),)
            )
        )
        intent = make_intent()
        first = engine.execute(intent, scenario="first")
        second = engine.execute(intent, scenario="second")
        self.assertIs(first, second)
        self.assertEqual(venue.submit_count, 1)

    def test_receipt_events_are_deterministically_sequenced(self) -> None:
        engine, _ = self.make_engine(
            plan=SimulatedOrderPlan(submit_status=OrderStatus.REJECTED)
        )
        receipt = engine.execute(make_intent(), scenario="events")
        self.assertEqual(
            [event.sequence for event in receipt.events],
            list(range(1, len(receipt.events) + 1)),
        )
        self.assertTrue(verify_receipt_payload(receipt.to_dict()))
