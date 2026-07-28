from __future__ import annotations

from decimal import Decimal
import unittest

from trade_execution_safety_lab.models import OrderType
from trade_execution_safety_lab.validation import validate_order

from tests.helpers import make_intent


def codes(intent: object) -> set[str]:
    return {issue.code for issue in validate_order(intent)}  # type: ignore[arg-type]


class ValidationTests(unittest.TestCase):
    def test_valid_limit_order_has_no_issues(self) -> None:
        self.assertEqual(validate_order(make_intent()), ())

    def test_quantity_must_be_positive(self) -> None:
        self.assertIn("quantity-not-positive", codes(make_intent(quantity="0")))

    def test_quantity_must_align_to_step(self) -> None:
        self.assertIn("quantity-step-mismatch", codes(make_intent(quantity="1.5")))

    def test_quantity_must_meet_minimum(self) -> None:
        self.assertIn("quantity-below-minimum", codes(make_intent(quantity="0.5")))

    def test_limit_order_requires_price(self) -> None:
        self.assertIn("limit-price-required", codes(make_intent(limit_price=None)))

    def test_limit_price_must_align_to_tick(self) -> None:
        self.assertIn("price-tick-mismatch", codes(make_intent(limit_price="25.03")))

    def test_market_order_rejects_limit_price(self) -> None:
        intent = make_intent(
            order_type=OrderType.MARKET,
            limit_price="25",
            reference_price="25",
        )
        self.assertIn("market-order-has-limit-price", codes(intent))

    def test_market_order_requires_positive_reference_price(self) -> None:
        intent = make_intent(
            order_type=OrderType.MARKET,
            limit_price=None,
            reference_price=None,
        )
        self.assertIn("reference-price-required", codes(intent))

    def test_minimum_notional_is_enforced(self) -> None:
        intent = make_intent(quantity="1", limit_price="5.00")
        self.assertIn("notional-below-minimum", codes(intent))

    def test_order_models_preserve_decimal_input(self) -> None:
        intent = make_intent(quantity="2", limit_price="25.00")
        self.assertEqual(intent.quantity * intent.limit_price, Decimal("50.00"))
