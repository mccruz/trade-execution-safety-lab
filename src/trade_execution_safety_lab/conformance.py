"""Reusable fail-closed checks for execution-venue adapters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .adapters import ExecutionVenue, VenueError, VenueErrorCategory
from .models import (
    OrderIntent,
    OrderSnapshot,
    OrderStatus,
    PositionSnapshot,
    VenueSafetyProfile,
)


@dataclass(frozen=True)
class ConformanceIssue:
    """A provider-neutral contract violation without provider payload data."""

    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def order_snapshot_issues(
    snapshot: OrderSnapshot,
    *,
    expected_intent: OrderIntent | None = None,
    expected_venue_order_id: str | None = None,
) -> tuple[ConformanceIssue, ...]:
    """Return invariant violations for one normalized order snapshot."""

    issues: list[ConformanceIssue] = []
    fill_ids = [fill.fill_id for fill in snapshot.fills]
    fill_sequences = [fill.sequence for fill in snapshot.fills]

    if snapshot.requested_quantity <= 0:
        issues.append(
            ConformanceIssue(
                "requested-quantity-not-positive",
                "Requested order quantity must be positive.",
            )
        )
    if snapshot.filled_quantity > snapshot.requested_quantity:
        issues.append(
            ConformanceIssue(
                "order-overfilled",
                "Observed fills exceed the requested quantity.",
            )
        )
    if len(fill_ids) != len(set(fill_ids)):
        issues.append(
            ConformanceIssue(
                "duplicate-fill-id",
                "Fill identifiers must be unique within an order.",
            )
        )
    if fill_sequences != sorted(fill_sequences) or len(fill_sequences) != len(
        set(fill_sequences)
    ):
        issues.append(
            ConformanceIssue(
                "invalid-fill-sequence",
                "Fill sequences must be unique and monotonically increasing.",
            )
        )

    if (
        snapshot.status is OrderStatus.FILLED
        and snapshot.filled_quantity != snapshot.requested_quantity
    ):
        issues.append(
            ConformanceIssue(
                "filled-status-quantity-mismatch",
                "A filled order must account for the complete requested quantity.",
            )
        )
    if (
        snapshot.filled_quantity == snapshot.requested_quantity
        and snapshot.status is not OrderStatus.FILLED
    ):
        issues.append(
            ConformanceIssue(
                "complete-fill-status-mismatch",
                "A completely filled order must have filled status.",
            )
        )
    if snapshot.status is OrderStatus.PARTIALLY_FILLED and not (
        0 < snapshot.filled_quantity < snapshot.requested_quantity
    ):
        issues.append(
            ConformanceIssue(
                "partial-status-quantity-mismatch",
                "A partially filled order must have bounded nonzero fills.",
            )
        )
    if snapshot.status is OrderStatus.ACCEPTED and snapshot.fills:
        issues.append(
            ConformanceIssue(
                "accepted-order-has-fills",
                "An accepted order with executions must be partially filled.",
            )
        )
    if snapshot.status is OrderStatus.REJECTED and snapshot.fills:
        issues.append(
            ConformanceIssue(
                "rejected-order-has-fills",
                "A rejected order cannot contain executions.",
            )
        )

    if expected_venue_order_id is not None and (
        snapshot.venue_order_id != expected_venue_order_id
    ):
        issues.append(
            ConformanceIssue(
                "venue-order-id-changed",
                "A venue lookup returned a different order identifier.",
            )
        )

    if expected_intent is not None:
        expected_fields = (
            snapshot.client_order_id == expected_intent.client_order_id,
            snapshot.instrument == expected_intent.instrument,
            snapshot.side is expected_intent.side,
            snapshot.order_type is expected_intent.order_type,
            snapshot.requested_quantity == expected_intent.quantity,
        )
        if not all(expected_fields):
            issues.append(
                ConformanceIssue(
                    "intent-snapshot-mismatch",
                    "The normalized order snapshot does not match its intent.",
                )
            )

    return tuple(issues)


def order_transition_issues(
    previous: OrderSnapshot,
    current: OrderSnapshot,
) -> tuple[ConformanceIssue, ...]:
    """Return violations between two observations of the same venue order."""

    issues = list(
        order_snapshot_issues(
            current,
            expected_venue_order_id=previous.venue_order_id,
        )
    )
    immutable_fields_match = (
        current.client_order_id == previous.client_order_id,
        current.instrument == previous.instrument,
        current.side is previous.side,
        current.order_type is previous.order_type,
        current.requested_quantity == previous.requested_quantity,
    )
    if not all(immutable_fields_match):
        issues.append(
            ConformanceIssue(
                "immutable-order-field-changed",
                "An immutable normalized order field changed between observations.",
            )
        )
    if current.sequence < previous.sequence:
        issues.append(
            ConformanceIssue(
                "order-sequence-regressed",
                "Order observation sequence cannot move backward.",
            )
        )

    current_fills = {fill.fill_id: fill for fill in current.fills}
    if any(current_fills.get(fill.fill_id) != fill for fill in previous.fills):
        issues.append(
            ConformanceIssue(
                "fill-history-regressed",
                "Previously observed fills must remain unchanged.",
            )
        )
    if previous.status.terminal and current.status is not previous.status:
        issues.append(
            ConformanceIssue(
                "terminal-status-changed",
                "A terminal order status cannot transition again.",
            )
        )
    if previous.status.terminal and current.fills != previous.fills:
        issues.append(
            ConformanceIssue(
                "terminal-fill-history-changed",
                "Fills cannot change after an order reaches terminal status.",
            )
        )
    return tuple(issues)


def position_snapshot_issues(
    positions: Iterable[PositionSnapshot],
) -> tuple[ConformanceIssue, ...]:
    """Return invariant violations for a venue position snapshot."""

    seen: set[str] = set()
    duplicates: set[str] = set()
    for position in positions:
        if position.symbol in seen:
            duplicates.add(position.symbol)
        seen.add(position.symbol)
    if duplicates:
        return (
            ConformanceIssue(
                "duplicate-position-symbol",
                "A venue snapshot must normalize to one position per symbol.",
            ),
        )
    return ()


def _raise_for_issues(issues: tuple[ConformanceIssue, ...]) -> None:
    if not issues:
        return
    codes = ",".join(dict.fromkeys(issue.code for issue in issues))
    raise VenueError(
        f"venue adapter conformance failed ({codes})",
        category=VenueErrorCategory.PROTOCOL,
        retryable=False,
    )


class ConformingVenue:
    """Validate a venue's normalized output before the engine can consume it."""

    def __init__(self, venue: ExecutionVenue) -> None:
        self._venue = venue
        self.name = f"conforming-{venue.name}"
        self.safety_profile: VenueSafetyProfile = venue.safety_profile
        self._last_by_order_id: dict[str, OrderSnapshot] = {}
        self._intent_by_order_id: dict[str, OrderIntent] = {}

    @property
    def network_used(self) -> bool:
        return self._venue.network_used

    def submit(self, intent: OrderIntent) -> OrderSnapshot:
        snapshot = self._venue.submit(intent)
        _raise_for_issues(order_snapshot_issues(snapshot, expected_intent=intent))
        self._remember(snapshot, intent=intent)
        return snapshot

    def poll(self, venue_order_id: str) -> OrderSnapshot:
        snapshot = self._venue.poll(venue_order_id)
        self._validate_observation(snapshot, expected_venue_order_id=venue_order_id)
        self._remember(snapshot)
        return snapshot

    def cancel(self, venue_order_id: str) -> OrderSnapshot:
        snapshot = self._venue.cancel(venue_order_id)
        self._validate_observation(snapshot, expected_venue_order_id=venue_order_id)
        self._remember(snapshot)
        return snapshot

    def find_by_client_order_id(
        self,
        client_order_id: str,
    ) -> OrderSnapshot | None:
        snapshot = self._venue.find_by_client_order_id(client_order_id)
        if snapshot is None:
            return None
        _raise_for_issues(order_snapshot_issues(snapshot))
        if snapshot.client_order_id != client_order_id:
            _raise_for_issues(
                (
                    ConformanceIssue(
                        "client-order-lookup-mismatch",
                        "A client-order lookup returned a different identifier.",
                    ),
                )
            )
        self._validate_observation(
            snapshot,
            expected_venue_order_id=snapshot.venue_order_id,
        )
        self._remember(snapshot)
        return snapshot

    def positions(self) -> tuple[PositionSnapshot, ...]:
        positions = tuple(self._venue.positions())
        _raise_for_issues(position_snapshot_issues(positions))
        return positions

    def _validate_observation(
        self,
        snapshot: OrderSnapshot,
        *,
        expected_venue_order_id: str,
    ) -> None:
        issues = list(
            order_snapshot_issues(
                snapshot,
                expected_intent=self._intent_by_order_id.get(expected_venue_order_id),
                expected_venue_order_id=expected_venue_order_id,
            )
        )
        previous = self._last_by_order_id.get(expected_venue_order_id)
        if previous is not None:
            issues.extend(order_transition_issues(previous, snapshot))
        _raise_for_issues(tuple(issues))

    def _remember(
        self,
        snapshot: OrderSnapshot,
        *,
        intent: OrderIntent | None = None,
    ) -> None:
        self._last_by_order_id[snapshot.venue_order_id] = snapshot
        if intent is not None:
            self._intent_by_order_id[snapshot.venue_order_id] = intent
