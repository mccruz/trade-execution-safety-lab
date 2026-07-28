from __future__ import annotations

from decimal import Decimal
import unittest

from trade_execution_safety_lab.adapters import VenueError, VenueErrorCategory
from trade_execution_safety_lab.models import OrderStatus, PositionSnapshot, Side
from trade_execution_safety_lab.simulator import (
    SimulatedOrderPlan,
    SimulatedVenue,
    SimulationStep,
)

from tests.helpers import make_intent


class SimulatorTests(unittest.TestCase):
    def test_submit_is_idempotent_by_client_order_id(self) -> None:
        venue = SimulatedVenue()
        intent = make_intent()
        first = venue.submit(intent)
        second = venue.submit(intent)
        self.assertEqual(first.venue_order_id, second.venue_order_id)
        self.assertEqual(venue.submit_count, 1)

    def test_scripted_full_fill_updates_position(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "25", fee="0.1"),)
            )
        )
        order = venue.submit(make_intent())
        order = venue.poll(order.venue_order_id)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(venue.positions()[0].quantity, Decimal("2"))

    def test_multiple_fills_use_weighted_average(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(
                    SimulationStep.fill("1", "20"),
                    SimulationStep.fill("1", "30"),
                )
            )
        )
        order = venue.submit(make_intent())
        order = venue.poll(order.venue_order_id)
        order = venue.poll(order.venue_order_id)
        self.assertEqual(order.average_fill_price, Decimal("25"))
        self.assertEqual(venue.positions()[0].average_price, Decimal("25"))

    def test_partial_close_preserves_prior_average_price(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("1", "30"),)
            ),
            initial_positions=(
                PositionSnapshot("DEMO-USD", Decimal("2"), Decimal("20"), 1),
            ),
        )
        order = venue.submit(make_intent(side=Side.SELL, quantity="1"))
        venue.poll(order.venue_order_id)
        position = venue.positions()[0]
        self.assertEqual(position.quantity, Decimal("1"))
        self.assertEqual(position.average_price, Decimal("20"))

    def test_crossing_through_zero_uses_new_fill_price(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("2", "30"),)
            ),
            initial_positions=(
                PositionSnapshot("DEMO-USD", Decimal("1"), Decimal("20"), 1),
            ),
        )
        order = venue.submit(make_intent(side=Side.SELL, quantity="2"))
        venue.poll(order.venue_order_id)
        position = venue.positions()[0]
        self.assertEqual(position.quantity, Decimal("-1"))
        self.assertEqual(position.average_price, Decimal("30"))

    def test_flat_positions_are_omitted(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("1", "25"),)
            ),
            initial_positions=(
                PositionSnapshot("DEMO-USD", Decimal("1"), Decimal("20"), 1),
            ),
        )
        order = venue.submit(make_intent(side=Side.SELL, quantity="1"))
        venue.poll(order.venue_order_id)
        self.assertEqual(venue.positions(), ())

    def test_cancel_can_race_with_fill(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                cancel_steps=(SimulationStep.fill("2", "25"),)
            )
        )
        order = venue.submit(make_intent())
        order = venue.cancel(order.venue_order_id)
        self.assertEqual(order.status, OrderStatus.FILLED)

    def test_overfill_is_rejected_by_simulator(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.fill("3", "25"),)
            )
        )
        order = venue.submit(make_intent(quantity="2"))
        with self.assertRaises(ValueError):
            venue.poll(order.venue_order_id)

    def test_disconnect_is_typed_as_transient(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                poll_steps=(SimulationStep.disconnect(),)
            )
        )
        order = venue.submit(make_intent())
        with self.assertRaises(VenueError) as raised:
            venue.poll(order.venue_order_id)
        self.assertEqual(raised.exception.category, VenueErrorCategory.TRANSIENT)
        self.assertTrue(raised.exception.retryable)

    def test_submit_error_does_not_create_order(self) -> None:
        venue = SimulatedVenue(
            default_plan=SimulatedOrderPlan(
                submit_error_category=VenueErrorCategory.RATE_LIMIT
            )
        )
        with self.assertRaises(VenueError):
            venue.submit(make_intent())
        self.assertEqual(venue.submit_count, 0)

    def test_unknown_order_id_is_protocol_error(self) -> None:
        venue = SimulatedVenue()
        with self.assertRaises(VenueError) as raised:
            venue.poll("SIM-MISSING")
        self.assertEqual(raised.exception.category, VenueErrorCategory.PROTOCOL)
