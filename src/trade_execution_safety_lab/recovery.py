"""Provider-neutral connection error classification and bounded recovery plans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .adapters import VenueError, VenueErrorCategory


class RecoveryAction(StrEnum):
    RETRY_WITH_BACKOFF = "retry-with-backoff"
    COOLDOWN = "cooldown"
    HUMAN_REVIEW = "human-review"


@dataclass(frozen=True)
class RecoveryPolicy:
    maximum_automatic_attempts: int = 3
    base_delay_seconds: int = 2
    maximum_delay_seconds: int = 30

    def __post_init__(self) -> None:
        if self.maximum_automatic_attempts < 0:
            raise ValueError("maximum_automatic_attempts cannot be negative")
        if self.base_delay_seconds < 1:
            raise ValueError("base_delay_seconds must be positive")
        if self.maximum_delay_seconds < self.base_delay_seconds:
            raise ValueError("maximum_delay_seconds cannot be below base delay")


@dataclass(frozen=True)
class RecoveryDecision:
    category: VenueErrorCategory
    action: RecoveryAction
    automatic: bool
    delay_seconds: int
    resync_required: bool
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "action": self.action.value,
            "automatic": self.automatic,
            "delay_seconds": self.delay_seconds,
            "resync_required": self.resync_required,
            "reason_code": self.reason_code,
        }


def classify_connection_failure(exc: BaseException) -> VenueErrorCategory:
    if isinstance(exc, VenueError):
        return exc.category
    if isinstance(exc, (TimeoutError, ConnectionResetError, BrokenPipeError, EOFError)):
        return VenueErrorCategory.TRANSIENT
    if isinstance(exc, PermissionError):
        return VenueErrorCategory.AUTHENTICATION
    if isinstance(exc, (ValueError, TypeError)):
        return VenueErrorCategory.PROTOCOL
    return VenueErrorCategory.UNKNOWN


def plan_recovery(
    exc: BaseException,
    *,
    attempt: int,
    policy: RecoveryPolicy | None = None,
) -> RecoveryDecision:
    if attempt < 1:
        raise ValueError("attempt must be at least one")
    selected = policy or RecoveryPolicy()
    category = classify_connection_failure(exc)

    if category in {VenueErrorCategory.TRANSIENT, VenueErrorCategory.RATE_LIMIT}:
        if attempt <= selected.maximum_automatic_attempts:
            multiplier = 2 ** (attempt - 1)
            if category is VenueErrorCategory.RATE_LIMIT:
                multiplier *= 2
            delay = min(
                selected.base_delay_seconds * multiplier,
                selected.maximum_delay_seconds,
            )
            return RecoveryDecision(
                category=category,
                action=(
                    RecoveryAction.COOLDOWN
                    if category is VenueErrorCategory.RATE_LIMIT
                    else RecoveryAction.RETRY_WITH_BACKOFF
                ),
                automatic=True,
                delay_seconds=delay,
                resync_required=True,
                reason_code=f"{category.value}-bounded-retry",
            )
        return RecoveryDecision(
            category=category,
            action=RecoveryAction.HUMAN_REVIEW,
            automatic=False,
            delay_seconds=0,
            resync_required=True,
            reason_code=f"{category.value}-retry-budget-exhausted",
        )

    return RecoveryDecision(
        category=category,
        action=RecoveryAction.HUMAN_REVIEW,
        automatic=False,
        delay_seconds=0,
        resync_required=True,
        reason_code=f"{category.value}-manual-review-required",
    )
