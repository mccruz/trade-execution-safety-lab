# Architecture and safety invariants

## Design objective

The lab separates execution reliability from trading decisions. A synthetic
intent enters a bounded state machine; the engine validates it, reconciles local
expectations to the simulated venue, submits at most once, observes or cancels
within fixed budgets, reconciles again, and writes a checksummed receipt.

The venue is the position source of truth. An order request, local expectation,
or cancellation request never overrides an observed fill.

![Execution safety architecture with fail-closed human review](../assets/architecture.svg)

## Components

| Component | Responsibility |
| --- | --- |
| `models.py` | Immutable decimal-safe intents, fills, snapshots, reconciliation reports, events, and receipts |
| `validation.py` | Quantity, tick, price, minimum quantity, and minimum notional checks |
| `adapters.py` | Provider-neutral venue protocol and typed failure categories |
| `simulator.py` | Deterministic order transitions and position accounting |
| `engine.py` | Idempotent, bounded, fail-closed orchestration |
| `reconciliation.py` | Venue-as-source-of-truth position comparison |
| `recovery.py` | Provider-neutral error classification and bounded recovery decisions |
| `receipts.py` | Canonical SHA-256 evidence and restrictive atomic persistence |
| `restart.py` | Duplicate-submission suppression after process restart |

## State and decision flow

1. Validate the synthetic intent before any venue method is called.
2. Compare expected positions with the venue snapshot. Drift blocks submission.
3. Recover by `client_order_id`, or submit exactly once when no venue order exists.
4. Poll within the configured budget.
5. If still open, request cancellation and observe within a second bounded budget.
6. Account for every observed fill, including fills that arrive during cancellation.
7. Reconcile expected post-fill exposure to venue positions.
8. Persist a canonical receipt. Only a complete fill with matched postflight
   reconciliation authorizes synthetic continuation.

## Fail-closed invariants

- Validation failure means zero order submissions.
- Preflight position drift means zero order submissions.
- A previously used client order ID cannot submit a second venue order.
- Cancellation requests do not imply cancellation success.
- Partial fills update exposure even when the remainder is cancelled.
- Unknown, disconnected, unreconciled, or tampered state never authorizes
  automatic continuation.
- Observation and retry budgets are finite.
- Receipt reset is restricted to a lab-owned directory sentinel.
- Evidence content declares `network_used: false` and
  `credentials_required: false`.

## Receipt integrity

Receipts serialize to canonical JSON with sorted keys and compact separators.
The SHA-256 digest covers every field except the digest itself. Files are written
to a restrictive temporary file, flushed and synced, then atomically replaced.
On restart, the stored receipt must verify before it can suppress resubmission.

This detects accidental or local post-write modification. It is not a substitute
for an external signature, append-only ledger, or trusted timestamp.

## Connection recovery

The recovery module separates classification from execution. Transient and
rate-limit failures receive finite backoff recommendations and require a full
state resynchronization. Authentication, protocol, unknown, and exhausted-retry
failures require human review. The version 1.0 lab never performs the retry or
opens a network connection.
