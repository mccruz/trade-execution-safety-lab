"""Provider-neutral execution models with decimal-safe accounting."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_SYMBOL = re.compile(r"^[A-Z][A-Z0-9-]{2,31}$")
_SAFE_PROFILE_VALUE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


def decimal_text(value: Decimal) -> str:
    """Return a non-exponent decimal representation for JSON evidence."""

    return format(value, "f")


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"

    @property
    def position_sign(self) -> Decimal:
        return Decimal("1") if self is Side.BUY else Decimal("-1")


class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(StrEnum):
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially-filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel-pending"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"

    @property
    def terminal(self) -> bool:
        return self in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }


class ReceiptOutcome(StrEnum):
    FILLED = "filled"
    CANCELLED = "cancelled"
    PARTIAL_FILL_DEFERRED = "partial-fill-deferred"
    REJECTED = "rejected"
    VALIDATION_BLOCKED = "validation-blocked"
    RECONCILIATION_BLOCKED = "reconciliation-blocked"
    VENUE_DEFERRED = "venue-deferred"
    UNKNOWN_DEFERRED = "unknown-deferred"


class ReconciliationStatus(StrEnum):
    MATCHED = "matched"
    DRIFT = "drift"


@dataclass(frozen=True)
class VenueSafetyProfile:
    """Non-secret execution boundary recorded with every receipt."""

    mode: str
    provider: str
    environment: str
    network_permitted: bool
    credentials_required: bool
    live_trading_permitted: bool = False

    def __post_init__(self) -> None:
        for name in ("mode", "provider", "environment"):
            if not _SAFE_PROFILE_VALUE.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} must be a safe lowercase identifier")
        if self.credentials_required and not self.network_permitted:
            raise ValueError("credentialed venues must permit network access")
        if self.live_trading_permitted:
            raise ValueError("live-trading venues are outside this project's scope")

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "provider": self.provider,
            "environment": self.environment,
            "network_permitted": self.network_permitted,
            "credentials_required": self.credentials_required,
            "live_trading_permitted": self.live_trading_permitted,
        }


OFFLINE_SIMULATION_PROFILE = VenueSafetyProfile(
    mode="offline-simulation",
    provider="simulated",
    environment="local",
    network_permitted=False,
    credentials_required=False,
)


@dataclass(frozen=True)
class Instrument:
    symbol: str
    price_tick: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal

    def __post_init__(self) -> None:
        if not _SAFE_SYMBOL.fullmatch(self.symbol):
            raise ValueError("instrument symbol must be an uppercase safe identifier")
        for name in (
            "price_tick",
            "quantity_step",
            "minimum_quantity",
            "minimum_notional",
        ):
            value = getattr(self, name)
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be positive")

    def to_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "price_tick": decimal_text(self.price_tick),
            "quantity_step": decimal_text(self.quantity_step),
            "minimum_quantity": decimal_text(self.minimum_quantity),
            "minimum_notional": decimal_text(self.minimum_notional),
        }


@dataclass(frozen=True)
class OrderIntent:
    client_order_id: str
    instrument: Instrument
    side: Side
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None = None
    reference_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.client_order_id):
            raise ValueError("client_order_id must be a safe 1-64 character identifier")
        for name in ("quantity", "limit_price", "reference_price"):
            value = getattr(self, name)
            if value is not None and not value.is_finite():
                raise ValueError(f"{name} must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "instrument": self.instrument.to_dict(),
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": decimal_text(self.quantity),
            "limit_price": (
                decimal_text(self.limit_price) if self.limit_price is not None else None
            ),
            "reference_price": (
                decimal_text(self.reference_price)
                if self.reference_price is not None
                else None
            ),
        }


@dataclass(frozen=True)
class Fill:
    fill_id: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    sequence: int

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.fill_id):
            raise ValueError("fill_id must be a safe identifier")
        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("fill price must be positive")
        if not self.fee.is_finite():
            raise ValueError("fill fee must be finite")
        if self.sequence < 1:
            raise ValueError("fill sequence must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "quantity": decimal_text(self.quantity),
            "price": decimal_text(self.price),
            "fee": decimal_text(self.fee),
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class OrderSnapshot:
    venue_order_id: str
    client_order_id: str
    instrument: Instrument
    side: Side
    order_type: OrderType
    requested_quantity: Decimal
    status: OrderStatus
    fills: tuple[Fill, ...] = ()
    reason: str | None = None
    sequence: int = 1

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.venue_order_id):
            raise ValueError("venue_order_id must be a safe identifier")
        if not _SAFE_IDENTIFIER.fullmatch(self.client_order_id):
            raise ValueError("client_order_id must be a safe identifier")
        if not self.requested_quantity.is_finite() or self.requested_quantity <= 0:
            raise ValueError("requested quantity must be positive")
        if self.sequence < 1:
            raise ValueError("order sequence must be positive")

    @property
    def filled_quantity(self) -> Decimal:
        return sum((fill.quantity for fill in self.fills), Decimal("0"))

    @property
    def remaining_quantity(self) -> Decimal:
        return max(self.requested_quantity - self.filled_quantity, Decimal("0"))

    @property
    def average_fill_price(self) -> Decimal | None:
        if not self.fills:
            return None
        notional = sum(
            (fill.quantity * fill.price for fill in self.fills), Decimal("0")
        )
        return notional / self.filled_quantity

    @property
    def total_fee(self) -> Decimal:
        return sum((fill.fee for fill in self.fills), Decimal("0"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue_order_id": self.venue_order_id,
            "client_order_id": self.client_order_id,
            "instrument": self.instrument.to_dict(),
            "side": self.side.value,
            "order_type": self.order_type.value,
            "requested_quantity": decimal_text(self.requested_quantity),
            "status": self.status.value,
            "filled_quantity": decimal_text(self.filled_quantity),
            "remaining_quantity": decimal_text(self.remaining_quantity),
            "average_fill_price": (
                decimal_text(self.average_fill_price)
                if self.average_fill_price is not None
                else None
            ),
            "total_fee": decimal_text(self.total_fee),
            "fills": [fill.to_dict() for fill in self.fills],
            "reason": self.reason,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    quantity: Decimal
    average_price: Decimal | None
    sequence: int

    def __post_init__(self) -> None:
        if not _SAFE_SYMBOL.fullmatch(self.symbol):
            raise ValueError("position symbol must be an uppercase safe identifier")
        if not self.quantity.is_finite():
            raise ValueError("position quantity must be finite")
        if self.average_price is not None and (
            not self.average_price.is_finite() or self.average_price < 0
        ):
            raise ValueError("average price cannot be negative")
        if self.sequence < 0:
            raise ValueError("position sequence cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": decimal_text(self.quantity),
            "average_price": (
                decimal_text(self.average_price)
                if self.average_price is not None
                else None
            ),
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "message": self.message}


@dataclass(frozen=True)
class ReconciliationItem:
    symbol: str
    expected_quantity: Decimal
    venue_quantity: Decimal

    @property
    def delta(self) -> Decimal:
        return self.venue_quantity - self.expected_quantity

    @property
    def matched(self) -> bool:
        return self.delta == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "expected_quantity": decimal_text(self.expected_quantity),
            "venue_quantity": decimal_text(self.venue_quantity),
            "delta": decimal_text(self.delta),
            "matched": self.matched,
        }


@dataclass(frozen=True)
class ReconciliationReport:
    status: ReconciliationStatus
    items: tuple[ReconciliationItem, ...]
    source_of_truth: str = "venue"
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "source_of_truth": self.source_of_truth,
            "reason_codes": list(self.reason_codes),
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class ExecutionEvent:
    sequence: int
    kind: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "message": self.message,
        }


@dataclass(frozen=True)
class ExecutionReceipt:
    schema_version: int
    receipt_id: str
    scenario: str
    intent: OrderIntent
    outcome: ReceiptOutcome
    next_action_authorized: bool
    reason_codes: tuple[str, ...]
    order: OrderSnapshot | None
    preflight: ReconciliationReport | None
    postflight: ReconciliationReport | None
    events: tuple[ExecutionEvent, ...] = field(default_factory=tuple)
    safety_profile: VenueSafetyProfile = OFFLINE_SIMULATION_PROFILE
    network_used: bool = False

    def __post_init__(self) -> None:
        if self.schema_version < 1:
            raise ValueError("receipt schema_version must be positive")
        if self.network_used and not self.safety_profile.network_permitted:
            raise ValueError(
                "network use cannot be recorded for a network-disabled venue"
            )

    def to_dict(self, *, include_receipt_id: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "scenario": self.scenario,
            **self.safety_profile.to_dict(),
            "network_used": self.network_used,
            "intent": self.intent.to_dict(),
            "outcome": self.outcome.value,
            "next_action_authorized": self.next_action_authorized,
            "reason_codes": list(self.reason_codes),
            "order": self.order.to_dict() if self.order is not None else None,
            "preflight_reconciliation": (
                self.preflight.to_dict() if self.preflight is not None else None
            ),
            "postflight_reconciliation": (
                self.postflight.to_dict() if self.postflight is not None else None
            ),
            "events": [event.to_dict() for event in self.events],
        }
        if include_receipt_id:
            payload["receipt_id"] = self.receipt_id
        return payload


def expected_positions_copy(
    expected: Mapping[str, Decimal],
) -> dict[str, Decimal]:
    return {symbol: Decimal(quantity) for symbol, quantity in expected.items()}
