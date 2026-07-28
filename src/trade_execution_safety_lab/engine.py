"""Fail-closed orchestration for deterministic execution-safety scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from .adapters import ExecutionVenue, VenueError
from .conformance import ConformingVenue, order_snapshot_issues
from .models import (
    ExecutionEvent,
    ExecutionReceipt,
    OrderIntent,
    OrderSnapshot,
    OrderStatus,
    ReceiptOutcome,
    ReconciliationReport,
    ReconciliationStatus,
    expected_positions_copy,
)
from .receipts import AtomicReceiptStore, finalize_receipt
from .reconciliation import expected_after_fills, reconcile_positions
from .validation import validate_order


@dataclass(frozen=True)
class ExecutionPolicy:
    """Bounded observation budgets; the engine never waits indefinitely."""

    maximum_order_polls: int = 2
    maximum_cancel_polls: int = 2

    def __post_init__(self) -> None:
        if self.maximum_order_polls < 0:
            raise ValueError("maximum_order_polls cannot be negative")
        if self.maximum_cancel_polls < 0:
            raise ValueError("maximum_cancel_polls cannot be negative")


class SafeExecutionEngine:
    """Execute one bounded intent while preserving fail-closed invariants."""

    def __init__(
        self,
        venue: ExecutionVenue,
        *,
        expected_positions: Mapping[str, Decimal] | None = None,
        receipt_store: AtomicReceiptStore,
        policy: ExecutionPolicy | None = None,
    ) -> None:
        self.venue = (
            venue if isinstance(venue, ConformingVenue) else ConformingVenue(venue)
        )
        if self.venue.safety_profile.live_trading_permitted:
            raise ValueError("live-trading venues are not supported")
        self.receipt_store = receipt_store
        self.policy = policy or ExecutionPolicy()
        self._expected_positions = expected_positions_copy(expected_positions or {})
        self._completed: dict[str, ExecutionReceipt] = {}

    @property
    def expected_positions(self) -> dict[str, Decimal]:
        return expected_positions_copy(self._expected_positions)

    def execute(self, intent: OrderIntent, *, scenario: str) -> ExecutionReceipt:
        """Execute once per client order id and persist checksummed evidence."""

        completed = self._completed.get(intent.client_order_id)
        if completed is not None:
            return completed

        events: list[ExecutionEvent] = []
        self._append_event(events, "intent.received", "Bounded order intent received.")

        issues = validate_order(intent)
        if issues:
            self._append_event(
                events,
                "validation.blocked",
                "Pre-submission validation blocked venue access.",
            )
            return self._finish(
                scenario=scenario,
                intent=intent,
                outcome=ReceiptOutcome.VALIDATION_BLOCKED,
                reason_codes=tuple(issue.code for issue in issues),
                order=None,
                preflight=None,
                postflight=None,
                events=events,
            )

        try:
            preflight = reconcile_positions(
                self._expected_positions,
                self.venue.positions(),
            )
        except VenueError as exc:
            self._append_event(
                events,
                "preflight.unavailable",
                f"Venue positions unavailable ({exc.category.value}); automation stopped.",
            )
            return self._finish(
                scenario=scenario,
                intent=intent,
                outcome=ReceiptOutcome.VENUE_DEFERRED,
                reason_codes=("preflight-position-unavailable", exc.category.value),
                order=None,
                preflight=None,
                postflight=None,
                events=events,
            )

        if preflight.status is ReconciliationStatus.DRIFT:
            self._append_event(
                events,
                "preflight.blocked",
                "Venue position drift blocked order submission.",
            )
            return self._finish(
                scenario=scenario,
                intent=intent,
                outcome=ReceiptOutcome.RECONCILIATION_BLOCKED,
                reason_codes=preflight.reason_codes,
                order=None,
                preflight=preflight,
                postflight=None,
                events=events,
            )

        self._append_event(
            events,
            "preflight.matched",
            "Expected positions match the venue source of truth.",
        )

        try:
            order = self.venue.find_by_client_order_id(intent.client_order_id)
        except VenueError as exc:
            self._append_event(
                events,
                "order.lookup-deferred",
                f"Existing-order lookup failed ({exc.category.value}); submission blocked.",
            )
            return self._finish(
                scenario=scenario,
                intent=intent,
                outcome=ReceiptOutcome.VENUE_DEFERRED,
                reason_codes=("existing-order-lookup-unavailable", exc.category.value),
                order=None,
                preflight=preflight,
                postflight=None,
                events=events,
            )
        if order is not None:
            if order_snapshot_issues(order, expected_intent=intent):
                self._append_event(
                    events,
                    "order.lookup-deferred",
                    "Recovered venue order did not match the requested intent.",
                )
                return self._finish(
                    scenario=scenario,
                    intent=intent,
                    outcome=ReceiptOutcome.VENUE_DEFERRED,
                    reason_codes=("existing-order-intent-mismatch",),
                    order=order,
                    preflight=preflight,
                    postflight=None,
                    events=events,
                )
            self._append_event(
                events,
                "order.recovered",
                "An existing venue order was recovered by client order id.",
            )
        else:
            try:
                order = self.venue.submit(intent)
            except VenueError as exc:
                self._append_event(
                    events,
                    "submit.deferred",
                    f"Venue submission failed ({exc.category.value}); retry not authorized.",
                )
                return self._finish(
                    scenario=scenario,
                    intent=intent,
                    outcome=ReceiptOutcome.VENUE_DEFERRED,
                    reason_codes=("submit-unconfirmed", exc.category.value),
                    order=None,
                    preflight=preflight,
                    postflight=None,
                    events=events,
                )
            self._append_event(
                events,
                "order.submitted",
                f"Venue reported order status {order.status.value}.",
            )

        order, outcome, state_reasons = self._observe_order(order, events)

        try:
            expected_after_order = expected_after_fills(
                self._expected_positions,
                intent,
                order,
            )
            postflight = reconcile_positions(
                expected_after_order,
                self.venue.positions(),
            )
        except VenueError as exc:
            self._append_event(
                events,
                "postflight.unavailable",
                f"Post-execution positions unavailable ({exc.category.value}).",
            )
            return self._finish(
                scenario=scenario,
                intent=intent,
                outcome=ReceiptOutcome.UNKNOWN_DEFERRED,
                reason_codes=(*state_reasons, "postflight-position-unavailable"),
                order=order,
                preflight=preflight,
                postflight=None,
                events=events,
            )

        if postflight.status is ReconciliationStatus.DRIFT:
            self._append_event(
                events,
                "postflight.blocked",
                "Observed fills do not reconcile to venue positions.",
            )
            outcome = ReceiptOutcome.RECONCILIATION_BLOCKED
            state_reasons = (*state_reasons, *postflight.reason_codes)
        else:
            self._expected_positions = expected_after_order
            self._append_event(
                events,
                "postflight.matched",
                "Observed fills reconcile to venue positions.",
            )

        return self._finish(
            scenario=scenario,
            intent=intent,
            outcome=outcome,
            reason_codes=state_reasons,
            order=order,
            preflight=preflight,
            postflight=postflight,
            events=events,
        )

    def _observe_order(
        self,
        order: OrderSnapshot,
        events: list[ExecutionEvent],
    ) -> tuple[OrderSnapshot, ReceiptOutcome, tuple[str, ...]]:
        if order.status.terminal:
            return self._classify_terminal(order)

        for _ in range(self.policy.maximum_order_polls):
            try:
                order = self.venue.poll(order.venue_order_id)
            except VenueError as exc:
                self._append_event(
                    events,
                    "order.observation-deferred",
                    f"Venue observation failed ({exc.category.value}).",
                )
                outcome = (
                    ReceiptOutcome.UNKNOWN_DEFERRED
                    if order.filled_quantity > 0
                    else ReceiptOutcome.VENUE_DEFERRED
                )
                return order, outcome, ("order-observation-unavailable",)
            self._append_event(
                events,
                "order.observed",
                f"Venue reported order status {order.status.value}.",
            )
            if order.status.terminal:
                return self._classify_terminal(order)

        self._append_event(
            events,
            "cancel.requested",
            "Observation budget ended; cancellation requested.",
        )
        try:
            order = self.venue.cancel(order.venue_order_id)
        except VenueError as exc:
            self._append_event(
                events,
                "cancel.unconfirmed",
                f"Cancellation could not be confirmed ({exc.category.value}).",
            )
            return order, ReceiptOutcome.UNKNOWN_DEFERRED, ("cancel-unconfirmed",)

        self._append_event(
            events,
            "cancel.observed",
            f"Venue reported order status {order.status.value}.",
        )
        if order.status.terminal:
            return self._classify_terminal(order)

        for _ in range(self.policy.maximum_cancel_polls):
            try:
                order = self.venue.poll(order.venue_order_id)
            except VenueError as exc:
                self._append_event(
                    events,
                    "cancel.observation-deferred",
                    f"Cancellation observation failed ({exc.category.value}).",
                )
                return (
                    order,
                    ReceiptOutcome.UNKNOWN_DEFERRED,
                    ("cancel-observation-unavailable",),
                )
            self._append_event(
                events,
                "cancel.observed",
                f"Venue reported order status {order.status.value}.",
            )
            if order.status.terminal:
                return self._classify_terminal(order)

        self._append_event(
            events,
            "cancel.unresolved",
            "Cancellation remained unresolved after the bounded observation budget.",
        )
        return order, ReceiptOutcome.UNKNOWN_DEFERRED, ("cancel-state-unresolved",)

    @staticmethod
    def _classify_terminal(
        order: OrderSnapshot,
    ) -> tuple[OrderSnapshot, ReceiptOutcome, tuple[str, ...]]:
        if order.status is OrderStatus.FILLED:
            return order, ReceiptOutcome.FILLED, ("order-filled",)
        if order.status is OrderStatus.REJECTED:
            return order, ReceiptOutcome.REJECTED, ("order-rejected",)
        if order.status in {OrderStatus.CANCELLED, OrderStatus.EXPIRED}:
            if order.filled_quantity > 0:
                return (
                    order,
                    ReceiptOutcome.PARTIAL_FILL_DEFERRED,
                    ("partial-fill-requires-review",),
                )
            reason = (
                "order-cancelled"
                if order.status is OrderStatus.CANCELLED
                else "order-expired"
            )
            return order, ReceiptOutcome.CANCELLED, (reason,)
        return order, ReceiptOutcome.UNKNOWN_DEFERRED, ("terminal-state-unmapped",)

    def _finish(
        self,
        *,
        scenario: str,
        intent: OrderIntent,
        outcome: ReceiptOutcome,
        reason_codes: tuple[str, ...],
        order: OrderSnapshot | None,
        preflight: ReconciliationReport | None,
        postflight: ReconciliationReport | None,
        events: list[ExecutionEvent],
    ) -> ExecutionReceipt:
        next_action_authorized = (
            outcome is ReceiptOutcome.FILLED
            and postflight is not None
            and postflight.status is ReconciliationStatus.MATCHED
        )
        self._append_event(
            events,
            "decision.recorded",
            (
                "Bounded workflow may continue."
                if next_action_authorized
                else "Automatic continuation is not authorized."
            ),
        )
        draft = ExecutionReceipt(
            schema_version=2,
            receipt_id="",
            scenario=scenario,
            intent=intent,
            outcome=outcome,
            next_action_authorized=next_action_authorized,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            order=order,
            preflight=preflight,
            postflight=postflight,
            events=tuple(events),
            safety_profile=self.venue.safety_profile,
            network_used=self.venue.network_used,
        )
        receipt = finalize_receipt(draft)
        self.receipt_store.write(receipt)
        self._completed[intent.client_order_id] = receipt
        return receipt

    @staticmethod
    def _append_event(
        events: list[ExecutionEvent],
        kind: str,
        message: str,
    ) -> None:
        events.append(
            ExecutionEvent(
                sequence=len(events) + 1,
                kind=kind,
                message=message,
            )
        )
