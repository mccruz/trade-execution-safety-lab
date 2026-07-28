"""Execution-venue protocol and bounded error types."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from .models import OrderIntent, OrderSnapshot, PositionSnapshot


class VenueErrorCategory(StrEnum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate-limit"
    AUTHENTICATION = "authentication"
    PROTOCOL = "protocol"
    UNKNOWN = "unknown"


class VenueError(RuntimeError):
    """A provider-neutral venue error without embedded credentials or payloads."""

    def __init__(
        self,
        message: str,
        *,
        category: VenueErrorCategory = VenueErrorCategory.UNKNOWN,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


@runtime_checkable
class ExecutionVenue(Protocol):
    name: str

    def submit(self, intent: OrderIntent) -> OrderSnapshot:
        """Submit once, keyed by client_order_id."""

    def poll(self, venue_order_id: str) -> OrderSnapshot:
        """Return the latest venue order state."""

    def cancel(self, venue_order_id: str) -> OrderSnapshot:
        """Request cancellation and return the immediately observed state."""

    def find_by_client_order_id(self, client_order_id: str) -> OrderSnapshot | None:
        """Resolve an existing venue order without submitting another one."""

    def positions(self) -> tuple[PositionSnapshot, ...]:
        """Return the venue position snapshot used as source of truth."""
