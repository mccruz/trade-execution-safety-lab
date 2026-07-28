from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest

from trade_execution_safety_lab.models import (
    Fill,
    Instrument,
    OrderSnapshot,
    OrderStatus,
    PositionSnapshot,
    decimal_text,
)

from tests.helpers import INSTRUMENT, make_intent


class ModelTests(unittest.TestCase):
    def test_decimal_text_avoids_exponent_notation(self) -> None:
        self.assertEqual(decimal_text(Decimal("1E-8")), "0.00000001")

    def test_instrument_requires_synthetic_safe_symbol(self) -> None:
        with self.assertRaises(ValueError):
            replace(INSTRUMENT, symbol="../../secret")

    def test_instrument_constraints_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            Instrument(
                symbol="DEMO-USD",
                price_tick=Decimal("0"),
                quantity_step=Decimal("1"),
                minimum_quantity=Decimal("1"),
                minimum_notional=Decimal("10"),
            )

    def test_instrument_constraints_must_be_finite(self) -> None:
        with self.assertRaises(ValueError):
            replace(INSTRUMENT, price_tick=Decimal("NaN"))

    def test_order_intent_rejects_unsafe_identifier(self) -> None:
        with self.assertRaises(ValueError):
            make_intent("../unsafe")

    def test_fill_rejects_non_positive_quantity(self) -> None:
        with self.assertRaises(ValueError):
            Fill("FILL-1", Decimal("0"), Decimal("25"), Decimal("0"), 1)

    def test_fill_rejects_nonfinite_values(self) -> None:
        with self.assertRaises(ValueError):
            Fill("FILL-1", Decimal("NaN"), Decimal("25"), Decimal("0"), 1)

    def test_fill_preserves_signed_fee_for_rebates(self) -> None:
        fill = Fill("FILL-1", Decimal("1"), Decimal("25"), Decimal("-0.01"), 1)
        self.assertEqual(fill.fee, Decimal("-0.01"))

    def test_order_snapshot_rejects_unsafe_identifiers(self) -> None:
        intent = make_intent()
        with self.assertRaises(ValueError):
            OrderSnapshot(
                venue_order_id="../unsafe",
                client_order_id=intent.client_order_id,
                instrument=intent.instrument,
                side=intent.side,
                order_type=intent.order_type,
                requested_quantity=intent.quantity,
                status=OrderStatus.ACCEPTED,
            )

    def test_order_snapshot_calculates_weighted_price_and_fee(self) -> None:
        intent = make_intent(quantity="3")
        order = OrderSnapshot(
            venue_order_id="SIM-1",
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=OrderStatus.FILLED,
            fills=(
                Fill("FILL-1", Decimal("1"), Decimal("20"), Decimal("0.1"), 1),
                Fill("FILL-2", Decimal("2"), Decimal("26"), Decimal("0.2"), 2),
            ),
        )
        self.assertEqual(order.filled_quantity, Decimal("3"))
        self.assertEqual(order.remaining_quantity, Decimal("0"))
        self.assertEqual(order.average_fill_price, Decimal("24"))
        self.assertEqual(order.total_fee, Decimal("0.3"))

    def test_terminal_statuses_are_explicit(self) -> None:
        self.assertTrue(OrderStatus.FILLED.terminal)
        self.assertTrue(OrderStatus.REJECTED.terminal)
        self.assertFalse(OrderStatus.CANCEL_PENDING.terminal)

    def test_position_requires_non_negative_sequence(self) -> None:
        with self.assertRaises(ValueError):
            PositionSnapshot("DEMO-USD", Decimal("0"), None, -1)
