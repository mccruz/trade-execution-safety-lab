from __future__ import annotations

from decimal import Decimal
import unittest

from trade_execution_safety_lab.models import (
    OrderStatus,
    PositionSnapshot,
    ReconciliationStatus,
    Side,
)
from trade_execution_safety_lab.reconciliation import (
    expected_after_fills,
    reconcile_positions,
)
from trade_execution_safety_lab.simulator import SimulatedOrderPlan, SimulatedVenue, SimulationStep

from tests.helpers import make_intent


class ReconciliationTests(unittest.TestCase):
    def test_empty_positions_match(self) -> None:
        report = reconcile_positions({}, ())
        self.assertEqual(report.status, ReconciliationStatus.MATCHED)
        self.assertEqual(report.source_of_truth, "venue")

    def test_quantity_drift_is_reported(self) -> None:
        report = reconcile_positions(
            {"DEMO-USD": Decimal("1")},
            (PositionSnapshot("DEMO-USD", Decimal("2"), Decimal("25"), 1),),
        )
        self.assertEqual(report.status, ReconciliationStatus.DRIFT)
        self.assertIn("position-quantity-drift", report.reason_codes)
        self.assertEqual(report.items[0].delta, Decimal("1"))

    def test_duplicate_venue_symbols_fail_closed(self) -> None:
        report = reconcile_positions(
            {},
            (
                PositionSnapshot("DEMO-USD", Decimal("1"), Decimal("25"), 1),
                PositionSnapshot("DEMO-USD", Decimal("1"), Decimal("25"), 2),
            ),
        )
        self.assertIn("duplicate-venue-position", report.reason_codes)

    def test_expected_after_buy_fill_increases_position(self) -> None:
        intent = make_intent()
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "25"),)
            )
        )
        order = venue.submit(intent)
        order = venue.poll(order.venue_order_id)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(
            expected_after_fills({}, intent, order)["DEMO-USD"],
            Decimal("2"),
        )

    def test_expected_after_sell_fill_decreases_position(self) -> None:
        intent = make_intent(side=Side.SELL)
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "25"),)
            )
        )
        order = venue.submit(intent)
        order = venue.poll(order.venue_order_id)
        self.assertEqual(
            expected_after_fills({"DEMO-USD": Decimal("3")}, intent, order)[
                "DEMO-USD"
            ],
            Decimal("1"),
        )
