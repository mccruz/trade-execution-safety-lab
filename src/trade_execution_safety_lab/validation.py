"""Pre-submission validation for price, quantity, and notional constraints."""

from __future__ import annotations

from decimal import Decimal

from .models import OrderIntent, OrderType, ValidationIssue


def _aligned(value: Decimal, step: Decimal) -> bool:
    return value % step == 0


def validate_order(intent: OrderIntent) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []

    if intent.quantity <= 0:
        issues.append(
            ValidationIssue(
                "quantity-not-positive",
                "quantity",
                "Quantity must be greater than zero.",
            )
        )
    else:
        if not _aligned(intent.quantity, intent.instrument.quantity_step):
            issues.append(
                ValidationIssue(
                    "quantity-step-mismatch",
                    "quantity",
                    "Quantity must align with the instrument quantity step.",
                )
            )
        if intent.quantity < intent.instrument.minimum_quantity:
            issues.append(
                ValidationIssue(
                    "quantity-below-minimum",
                    "quantity",
                    "Quantity is below the instrument minimum.",
                )
            )

    effective_price: Decimal | None = None
    if intent.order_type is OrderType.LIMIT:
        if intent.limit_price is None:
            issues.append(
                ValidationIssue(
                    "limit-price-required",
                    "limit_price",
                    "Limit orders require a limit price.",
                )
            )
        elif intent.limit_price <= 0:
            issues.append(
                ValidationIssue(
                    "price-not-positive",
                    "limit_price",
                    "Limit price must be greater than zero.",
                )
            )
        else:
            effective_price = intent.limit_price
            if not _aligned(intent.limit_price, intent.instrument.price_tick):
                issues.append(
                    ValidationIssue(
                        "price-tick-mismatch",
                        "limit_price",
                        "Limit price must align with the instrument price tick.",
                    )
                )
    elif intent.limit_price is not None:
        issues.append(
            ValidationIssue(
                "market-order-has-limit-price",
                "limit_price",
                "Market orders cannot include a limit price.",
            )
        )

    if intent.order_type is OrderType.MARKET:
        if intent.reference_price is None or intent.reference_price <= 0:
            issues.append(
                ValidationIssue(
                    "reference-price-required",
                    "reference_price",
                    "A positive reference price is required for market-order validation.",
                )
            )
        else:
            effective_price = intent.reference_price

    if (
        intent.quantity > 0
        and effective_price is not None
        and effective_price > 0
        and intent.quantity * effective_price < intent.instrument.minimum_notional
    ):
        issues.append(
            ValidationIssue(
                "notional-below-minimum",
                "quantity",
                "Order notional is below the instrument minimum.",
            )
        )

    return tuple(issues)
