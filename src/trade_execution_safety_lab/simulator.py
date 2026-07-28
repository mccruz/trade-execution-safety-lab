"""Deterministic broker/exchange simulator used by every demo and test."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from .adapters import VenueError, VenueErrorCategory
from .models import (
    OFFLINE_SIMULATION_PROFILE,
    Fill,
    OrderIntent,
    OrderSnapshot,
    OrderStatus,
    PositionSnapshot,
)


class SimulationStepKind(StrEnum):
    FILL = "fill"
    NO_CHANGE = "no-change"
    CANCEL = "cancel"
    REJECT = "reject"
    EXPIRE = "expire"
    DISCONNECT = "disconnect"


@dataclass(frozen=True)
class SimulationStep:
    kind: SimulationStepKind
    quantity: Decimal = Decimal("0")
    price: Decimal | None = None
    fee: Decimal = Decimal("0")
    reason: str = ""

    @classmethod
    def fill(
        cls,
        quantity: str | Decimal,
        price: str | Decimal,
        *,
        fee: str | Decimal = "0",
        reason: str = "",
    ) -> "SimulationStep":
        return cls(
            kind=SimulationStepKind.FILL,
            quantity=Decimal(quantity),
            price=Decimal(price),
            fee=Decimal(fee),
            reason=reason,
        )

    @classmethod
    def no_change(cls, reason: str = "") -> "SimulationStep":
        return cls(SimulationStepKind.NO_CHANGE, reason=reason)

    @classmethod
    def cancel(cls, reason: str = "venue-confirmed-cancel") -> "SimulationStep":
        return cls(SimulationStepKind.CANCEL, reason=reason)

    @classmethod
    def reject(cls, reason: str = "synthetic-rejection") -> "SimulationStep":
        return cls(SimulationStepKind.REJECT, reason=reason)

    @classmethod
    def expire(cls, reason: str = "synthetic-expiry") -> "SimulationStep":
        return cls(SimulationStepKind.EXPIRE, reason=reason)

    @classmethod
    def disconnect(cls, reason: str = "synthetic-disconnect") -> "SimulationStep":
        return cls(SimulationStepKind.DISCONNECT, reason=reason)


@dataclass(frozen=True)
class SimulatedOrderPlan:
    submit_status: OrderStatus = OrderStatus.ACCEPTED
    submit_reason: str = ""
    poll_steps: tuple[SimulationStep, ...] = ()
    cancel_steps: tuple[SimulationStep, ...] = (
        SimulationStep(kind=SimulationStepKind.CANCEL, reason="venue-confirmed-cancel"),
    )
    submit_error_category: VenueErrorCategory | None = None

    def __post_init__(self) -> None:
        if self.submit_status not in {OrderStatus.ACCEPTED, OrderStatus.REJECTED}:
            raise ValueError("simulated submit status must be accepted or rejected")


@dataclass
class _OrderRuntime:
    intent: OrderIntent
    plan: SimulatedOrderPlan
    snapshot: OrderSnapshot
    poll_index: int = 0
    cancel_index: int = 0
    cancel_requested: bool = False


@dataclass
class _PositionState:
    quantity: Decimal
    average_price: Decimal | None
    sequence: int


class SimulatedVenue:
    """A single-process venue with explicit scripted state transitions."""

    name = "deterministic-simulated-venue"
    safety_profile = OFFLINE_SIMULATION_PROFILE

    def __init__(
        self,
        *,
        plans: dict[str, SimulatedOrderPlan] | None = None,
        default_plan: SimulatedOrderPlan | None = None,
        initial_positions: tuple[PositionSnapshot, ...] = (),
    ) -> None:
        self._plans = dict(plans or {})
        self._default_plan = default_plan or SimulatedOrderPlan()
        self._orders: dict[str, _OrderRuntime] = {}
        self._client_to_venue: dict[str, str] = {}
        self._positions: dict[str, _PositionState] = {
            position.symbol: _PositionState(
                quantity=position.quantity,
                average_price=position.average_price,
                sequence=position.sequence,
            )
            for position in initial_positions
        }
        self._next_order_number = 1
        self._sequence = max(
            (position.sequence for position in initial_positions),
            default=0,
        )
        self.submit_count = 0
        self.cancel_count = 0
        self.poll_count = 0

    @property
    def network_used(self) -> bool:
        return False

    def submit(self, intent: OrderIntent) -> OrderSnapshot:
        existing = self.find_by_client_order_id(intent.client_order_id)
        if existing is not None:
            return existing

        plan = self._plans.get(intent.client_order_id, self._default_plan)
        if plan.submit_error_category is not None:
            raise VenueError(
                "simulated submit failure",
                category=plan.submit_error_category,
                retryable=plan.submit_error_category
                in {VenueErrorCategory.TRANSIENT, VenueErrorCategory.RATE_LIMIT},
            )

        venue_order_id = f"SIM-{self._next_order_number:04d}"
        self._next_order_number += 1
        self.submit_count += 1
        self._sequence += 1
        snapshot = OrderSnapshot(
            venue_order_id=venue_order_id,
            client_order_id=intent.client_order_id,
            instrument=intent.instrument,
            side=intent.side,
            order_type=intent.order_type,
            requested_quantity=intent.quantity,
            status=plan.submit_status,
            reason=plan.submit_reason or None,
            sequence=self._sequence,
        )
        runtime = _OrderRuntime(intent=intent, plan=plan, snapshot=snapshot)
        self._orders[venue_order_id] = runtime
        self._client_to_venue[intent.client_order_id] = venue_order_id
        return snapshot

    def poll(self, venue_order_id: str) -> OrderSnapshot:
        runtime = self._runtime(venue_order_id)
        self.poll_count += 1
        if runtime.snapshot.status.terminal:
            return runtime.snapshot

        if runtime.cancel_requested:
            step = self._next_cancel_step(runtime)
        else:
            step = self._next_poll_step(runtime)
        if step is None:
            return runtime.snapshot
        return self._apply_step(runtime, step)

    def cancel(self, venue_order_id: str) -> OrderSnapshot:
        runtime = self._runtime(venue_order_id)
        self.cancel_count += 1
        if runtime.snapshot.status.terminal:
            return runtime.snapshot
        runtime.cancel_requested = True
        self._sequence += 1
        runtime.snapshot = replace(
            runtime.snapshot,
            status=OrderStatus.CANCEL_PENDING,
            reason="cancel-requested",
            sequence=self._sequence,
        )
        step = self._next_cancel_step(runtime)
        if step is None:
            step = SimulationStep.cancel()
        return self._apply_step(runtime, step)

    def find_by_client_order_id(self, client_order_id: str) -> OrderSnapshot | None:
        venue_order_id = self._client_to_venue.get(client_order_id)
        if venue_order_id is None:
            return None
        return self._orders[venue_order_id].snapshot

    def positions(self) -> tuple[PositionSnapshot, ...]:
        return tuple(
            PositionSnapshot(
                symbol=symbol,
                quantity=state.quantity,
                average_price=state.average_price,
                sequence=state.sequence,
            )
            for symbol, state in sorted(self._positions.items())
            if state.quantity != 0
        )

    def set_position(
        self,
        symbol: str,
        quantity: Decimal,
        average_price: Decimal | None,
    ) -> None:
        self._sequence += 1
        self._positions[symbol] = _PositionState(
            quantity=Decimal(quantity),
            average_price=average_price,
            sequence=self._sequence,
        )
    def _runtime(self, venue_order_id: str) -> _OrderRuntime:
        try:
            return self._orders[venue_order_id]
        except KeyError as exc:
            raise VenueError(
                "simulated order was not found",
                category=VenueErrorCategory.PROTOCOL,
                retryable=False,
            ) from exc

    @staticmethod
    def _next_poll_step(runtime: _OrderRuntime) -> SimulationStep | None:
        if runtime.poll_index >= len(runtime.plan.poll_steps):
            return None
        step = runtime.plan.poll_steps[runtime.poll_index]
        runtime.poll_index += 1
        return step

    @staticmethod
    def _next_cancel_step(runtime: _OrderRuntime) -> SimulationStep | None:
        if runtime.cancel_index >= len(runtime.plan.cancel_steps):
            return None
        step = runtime.plan.cancel_steps[runtime.cancel_index]
        runtime.cancel_index += 1
        return step

    def _apply_step(
        self,
        runtime: _OrderRuntime,
        step: SimulationStep,
    ) -> OrderSnapshot:
        if step.kind is SimulationStepKind.DISCONNECT:
            raise VenueError(
                "simulated connection interruption",
                category=VenueErrorCategory.TRANSIENT,
                retryable=True,
            )

        self._sequence += 1
        snapshot = runtime.snapshot
        if step.kind is SimulationStepKind.NO_CHANGE:
            runtime.snapshot = replace(
                snapshot,
                reason=step.reason or snapshot.reason,
                sequence=self._sequence,
            )
            return runtime.snapshot

        if step.kind is SimulationStepKind.CANCEL:
            runtime.snapshot = replace(
                snapshot,
                status=OrderStatus.CANCELLED,
                reason=step.reason or "venue-confirmed-cancel",
                sequence=self._sequence,
            )
            return runtime.snapshot

        if step.kind is SimulationStepKind.REJECT:
            runtime.snapshot = replace(
                snapshot,
                status=OrderStatus.REJECTED,
                reason=step.reason or "synthetic-rejection",
                sequence=self._sequence,
            )
            return runtime.snapshot

        if step.kind is SimulationStepKind.EXPIRE:
            runtime.snapshot = replace(
                snapshot,
                status=OrderStatus.EXPIRED,
                reason=step.reason or "synthetic-expiry",
                sequence=self._sequence,
            )
            return runtime.snapshot

        if step.kind is not SimulationStepKind.FILL:
            raise AssertionError(f"unsupported simulation step: {step.kind}")
        if step.price is None:
            raise ValueError("fill simulation step requires a price")
        if step.quantity <= 0:
            raise ValueError("fill simulation step requires a positive quantity")
        if step.quantity > snapshot.remaining_quantity:
            raise ValueError("fill simulation step exceeds remaining order quantity")

        fill = Fill(
            fill_id=f"FILL-{snapshot.venue_order_id}-{len(snapshot.fills) + 1}",
            quantity=step.quantity,
            price=step.price,
            fee=step.fee,
            sequence=self._sequence,
        )
        fills = (*snapshot.fills, fill)
        filled_quantity = sum((item.quantity for item in fills), Decimal("0"))
        status = (
            OrderStatus.FILLED
            if filled_quantity == snapshot.requested_quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        runtime.snapshot = replace(
            snapshot,
            status=status,
            fills=fills,
            reason=step.reason or None,
            sequence=self._sequence,
        )
        self._apply_fill_to_position(runtime.intent, fill)
        return runtime.snapshot

    def _apply_fill_to_position(self, intent: OrderIntent, fill: Fill) -> None:
        symbol = intent.instrument.symbol
        state = self._positions.get(
            symbol,
            _PositionState(Decimal("0"), None, self._sequence),
        )
        signed_fill = intent.side.position_sign * fill.quantity
        prior_quantity = state.quantity
        new_quantity = prior_quantity + signed_fill

        if prior_quantity == 0 or prior_quantity * signed_fill > 0:
            prior_notional = (
                abs(prior_quantity) * (state.average_price or Decimal("0"))
            )
            fill_notional = abs(signed_fill) * fill.price
            average_price = (prior_notional + fill_notional) / abs(new_quantity)
        elif new_quantity == 0:
            average_price = None
        elif prior_quantity * new_quantity > 0:
            average_price = state.average_price
        else:
            average_price = fill.price

        self._positions[symbol] = _PositionState(
            quantity=new_quantity,
            average_price=average_price,
            sequence=self._sequence,
        )
