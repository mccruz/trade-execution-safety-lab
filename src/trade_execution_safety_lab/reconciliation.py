"""Venue-as-source-of-truth position reconciliation."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping

from .models import (
    OrderIntent,
    OrderSnapshot,
    PositionSnapshot,
    ReconciliationItem,
    ReconciliationReport,
    ReconciliationStatus,
    expected_positions_copy,
)


def reconcile_positions(
    expected: Mapping[str, Decimal],
    venue_positions: Iterable[PositionSnapshot],
) -> ReconciliationReport:
    actual: dict[str, Decimal] = {}
    duplicate_symbols: set[str] = set()
    for position in venue_positions:
        if position.symbol in actual:
            duplicate_symbols.add(position.symbol)
        actual[position.symbol] = position.quantity

    symbols = sorted(set(expected) | set(actual))
    items = tuple(
        ReconciliationItem(
            symbol=symbol,
            expected_quantity=Decimal(expected.get(symbol, Decimal("0"))),
            venue_quantity=Decimal(actual.get(symbol, Decimal("0"))),
        )
        for symbol in symbols
    )

    reason_codes: list[str] = []
    if duplicate_symbols:
        reason_codes.append("duplicate-venue-position")
    if any(not item.matched for item in items):
        reason_codes.append("position-quantity-drift")

    status = (
        ReconciliationStatus.MATCHED
        if not reason_codes
        else ReconciliationStatus.DRIFT
    )
    return ReconciliationReport(
        status=status,
        items=items,
        reason_codes=tuple(reason_codes),
    )


def expected_after_fills(
    expected: Mapping[str, Decimal],
    intent: OrderIntent,
    order: OrderSnapshot,
) -> dict[str, Decimal]:
    updated = expected_positions_copy(expected)
    prior = updated.get(intent.instrument.symbol, Decimal("0"))
    updated[intent.instrument.symbol] = (
        prior + intent.side.position_sign * order.filled_quantity
    )
    return updated
