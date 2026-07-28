from __future__ import annotations

import unittest

from trade_execution_safety_lab.adapters import VenueError, VenueErrorCategory
from trade_execution_safety_lab.recovery import (
    RecoveryAction,
    RecoveryPolicy,
    classify_connection_failure,
    plan_recovery,
)


class RecoveryTests(unittest.TestCase):
    def test_timeout_is_transient(self) -> None:
        self.assertEqual(
            classify_connection_failure(TimeoutError()),
            VenueErrorCategory.TRANSIENT,
        )

    def test_permission_error_requires_authentication_review(self) -> None:
        self.assertEqual(
            classify_connection_failure(PermissionError()),
            VenueErrorCategory.AUTHENTICATION,
        )

    def test_value_error_is_protocol_failure(self) -> None:
        self.assertEqual(
            classify_connection_failure(ValueError()),
            VenueErrorCategory.PROTOCOL,
        )

    def test_typed_venue_error_category_is_preserved(self) -> None:
        error = VenueError("rate", category=VenueErrorCategory.RATE_LIMIT)
        self.assertEqual(
            classify_connection_failure(error),
            VenueErrorCategory.RATE_LIMIT,
        )

    def test_transient_retry_uses_exponential_backoff(self) -> None:
        first = plan_recovery(TimeoutError(), attempt=1)
        third = plan_recovery(TimeoutError(), attempt=3)
        self.assertEqual(first.action, RecoveryAction.RETRY_WITH_BACKOFF)
        self.assertEqual(first.delay_seconds, 2)
        self.assertEqual(third.delay_seconds, 8)
        self.assertTrue(third.resync_required)

    def test_rate_limit_uses_longer_cooldown(self) -> None:
        decision = plan_recovery(
            VenueError("rate", category=VenueErrorCategory.RATE_LIMIT),
            attempt=1,
        )
        self.assertEqual(decision.action, RecoveryAction.COOLDOWN)
        self.assertEqual(decision.delay_seconds, 4)

    def test_retry_budget_exhaustion_requires_human_review(self) -> None:
        decision = plan_recovery(TimeoutError(), attempt=4)
        self.assertEqual(decision.action, RecoveryAction.HUMAN_REVIEW)
        self.assertFalse(decision.automatic)

    def test_authentication_failure_is_never_automatic(self) -> None:
        decision = plan_recovery(PermissionError(), attempt=1)
        self.assertEqual(decision.action, RecoveryAction.HUMAN_REVIEW)
        self.assertFalse(decision.automatic)

    def test_delay_is_capped(self) -> None:
        decision = plan_recovery(
            TimeoutError(),
            attempt=5,
            policy=RecoveryPolicy(
                maximum_automatic_attempts=5,
                base_delay_seconds=10,
                maximum_delay_seconds=20,
            ),
        )
        self.assertEqual(decision.delay_seconds, 20)

    def test_invalid_policy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RecoveryPolicy(maximum_automatic_attempts=-1)

    def test_attempt_numbers_start_at_one(self) -> None:
        with self.assertRaises(ValueError):
            plan_recovery(TimeoutError(), attempt=0)
