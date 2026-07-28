"""Restart decisions that suppress duplicate submissions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .adapters import ExecutionVenue
from .receipts import AtomicReceiptStore


class RestartAction(StrEnum):
    RETURN_VERIFIED_RECEIPT = "return-verified-receipt"
    RECONCILE_EXISTING_ORDER = "reconcile-existing-order"
    SAFE_TO_SUBMIT = "safe-to-submit"


@dataclass(frozen=True)
class RestartDecision:
    action: RestartAction
    client_order_id: str
    reason_code: str
    receipt_id: str | None = None
    venue_order_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "client_order_id": self.client_order_id,
            "reason_code": self.reason_code,
            "receipt_id": self.receipt_id,
            "venue_order_id": self.venue_order_id,
        }


def inspect_restart(
    store: AtomicReceiptStore,
    venue: ExecutionVenue,
    client_order_id: str,
) -> RestartDecision:
    stored = store.read_verified(client_order_id)
    if stored is not None:
        return RestartDecision(
            action=RestartAction.RETURN_VERIFIED_RECEIPT,
            client_order_id=client_order_id,
            reason_code="verified-receipt-prevents-resubmission",
            receipt_id=str(stored["receipt_id"]),
        )

    existing = venue.find_by_client_order_id(client_order_id)
    if existing is not None:
        return RestartDecision(
            action=RestartAction.RECONCILE_EXISTING_ORDER,
            client_order_id=client_order_id,
            reason_code="venue-order-exists-without-local-receipt",
            venue_order_id=existing.venue_order_id,
        )

    return RestartDecision(
        action=RestartAction.SAFE_TO_SUBMIT,
        client_order_id=client_order_id,
        reason_code="no-local-receipt-or-venue-order",
    )
