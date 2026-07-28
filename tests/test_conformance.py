from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from tests.helpers import make_intent
from trade_execution_safety_lab.adapters import VenueError, VenueErrorCategory
from trade_execution_safety_lab.conformance import (
    ConformingVenue,
    order_snapshot_issues,
    order_transition_issues,
)
from trade_execution_safety_lab.models import (
    Fill,
    OrderSnapshot,
    OrderStatus,
    PositionSnapshot,
)
from trade_execution_safety_lab.simulator import SimulatedOrderPlan, SimulatedVenue


class WrongClientIdVenue(SimulatedVenue):
    def submit(self, intent):
        return replace(super().submit(intent), client_order_id="OTHER-ORDER")


class DuplicatePositionVenue(SimulatedVenue):
    def positions(self):
        return (
            PositionSnapshot("DEMO-USD", Decimal("1"), Decimal("25"), 1),
            PositionSnapshot("DEMO-USD", Decimal("2"), Decimal("25"), 2),
        )


class ConformanceTests(unittest.TestCase):
    def test_valid_simulator_can_be_wrapped(self) -> None:
        venue = ConformingVenue(
            SimulatedVenue(
                default_plan=SimulatedOrderPlan(
                    poll_steps=(),
                )
            )
        )
        order = venue.submit(make_intent())
        self.assertEqual(order.client_order_id, "TEST-ORDER")
        self.assertFalse(venue.network_used)

    def test_submit_mismatch_fails_closed(self) -> None:
        with self.assertRaises(VenueError) as raised:
            ConformingVenue(WrongClientIdVenue()).submit(make_intent())
        self.assertEqual(raised.exception.category, VenueErrorCategory.PROTOCOL)

    def test_duplicate_positions_fail_closed(self) -> None:
        with self.assertRaises(VenueError) as raised:
            ConformingVenue(DuplicatePositionVenue()).positions()
        self.assertIn("duplicate-position-symbol", str(raised.exception))

    def test_overfill_is_a_contract_violation(self) -> None:
        intent = make_intent(quantity="1")
        snapshot = OrderSnapshot(
            venue_order_id="ORDER-1",
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=OrderStatus.FILLED,
            fills=(
                Fill(
                    "FILL-1",
                    Decimal("2"),
                    Decimal("25"),
                    Decimal("0"),
                    1,
                ),
            ),
        )
        codes = {issue.code for issue in order_snapshot_issues(snapshot)}
        self.assertIn("order-overfilled", codes)

    def test_fill_history_cannot_regress(self) -> None:
        intent = make_intent(quantity="2")
        previous = OrderSnapshot(
            venue_order_id="ORDER-1",
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=OrderStatus.PARTIALLY_FILLED,
            fills=(
                Fill(
                    "FILL-1",
                    Decimal("1"),
                    Decimal("25"),
                    Decimal("0"),
                    1,
                ),
            ),
            sequence=1,
        )
        current = replace(
            previous,
            status=OrderStatus.ACCEPTED,
            fills=(),
            sequence=2,
        )
        codes = {issue.code for issue in order_transition_issues(previous, current)}
        self.assertIn("fill-history-regressed", codes)

    def test_terminal_status_cannot_change(self) -> None:
        intent = make_intent(quantity="1")
        filled = OrderSnapshot(
            venue_order_id="ORDER-1",
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=OrderStatus.FILLED,
            fills=(
                Fill(
                    "FILL-1",
                    Decimal("1"),
                    Decimal("25"),
                    Decimal("0"),
                    1,
                ),
            ),
            sequence=1,
        )
        changed = replace(filled, status=OrderStatus.CANCELLED, sequence=2)
        codes = {issue.code for issue in order_transition_issues(filled, changed)}
        self.assertIn("terminal-status-changed", codes)

    def test_complete_fill_requires_filled_status(self) -> None:
        intent = make_intent(quantity="1")
        cancelled = OrderSnapshot(
            venue_order_id="ORDER-1",
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=OrderStatus.CANCELLED,
            fills=(
                Fill(
                    "FILL-1",
                    Decimal("1"),
                    Decimal("25"),
                    Decimal("0"),
                    1,
                ),
            ),
        )
        codes = {issue.code for issue in order_snapshot_issues(cancelled)}
        self.assertIn("complete-fill-status-mismatch", codes)

    def test_terminal_fill_history_cannot_grow(self) -> None:
        intent = make_intent(quantity="2")
        cancelled = OrderSnapshot(
            venue_order_id="ORDER-1",
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=OrderStatus.CANCELLED,
            fills=(
                Fill(
                    "FILL-1",
                    Decimal("1"),
                    Decimal("25"),
                    Decimal("0"),
                    1,
                ),
            ),
            sequence=1,
        )
        changed = replace(
            cancelled,
            fills=(
                *cancelled.fills,
                Fill(
                    "FILL-2",
                    Decimal("1"),
                    Decimal("25"),
                    Decimal("0"),
                    2,
                ),
            ),
            status=OrderStatus.FILLED,
            sequence=2,
        )
        codes = {issue.code for issue in order_transition_issues(cancelled, changed)}
        self.assertIn("terminal-fill-history-changed", codes)
