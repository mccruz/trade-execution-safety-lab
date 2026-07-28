# Deterministic scenario catalog

Every scenario uses `DEMO-USD`, synthetic orders and fills, an in-memory venue,
and no clock, randomness, network, or credentials.

| Scenario | Injected condition | Expected outcome | Why |
| --- | --- | --- | --- |
| `full-fill` | Entire quantity fills during observation | `filled` | Postflight positions match, so the synthetic workflow may continue |
| `partial-fill-cancel` | One unit fills; remainder cancels | `partial-fill-deferred` | Exposure is reconciled, but a human decides what happens next |
| `cancel-fill-race` | Full fill arrives with the cancel request | `filled` | The venue fill is authoritative; cancel intent does not erase execution |
| `unresolved-cancel` | Order remains cancel-pending beyond the budget | `unknown-deferred` | The engine cannot prove the terminal state |
| `rejected-order` | Venue rejects on submission | `rejected` | Rejection is recorded and never retried automatically |
| `position-drift` | Venue has an unexpected open position | `reconciliation-blocked` | Submission stops before creating additional exposure |
| `invalid-minimum` | Quantity is zero | `validation-blocked` | Local validation prevents venue access |
| `transient-disconnect` | Observation raises a typed connection interruption | `venue-deferred` | The order state is unconfirmed; automatic continuation stops |

## Restart evidence

The complete demo reopens the `full-fill` receipt through the restart inspector.
Because the checksum is valid, the decision is
`return-verified-receipt`—not `safe-to-submit`. Tests also cover the other two
restart branches:

- A venue order without a local receipt requires reconciliation.
- Only the absence of both a verified receipt and venue order is safe to submit.

## Recovery evidence

The summary includes three provider-neutral recovery decisions:

- First transient failure: bounded automatic backoff plus required resync.
- Transient failure after the retry budget: human review.
- Authentication failure: immediate human review.

These are decision records. The lab deliberately does not sleep, retry, or
connect to a service.

## Inspect the generated evidence

```bash
trade-safety-lab demo --output-dir demo-output --reset
open demo-output/summary.md  # macOS
```

On Windows or Linux, open `demo-output/summary.md` in any text editor. The
adjacent JSON summary is machine-readable, and each receipt can be verified with
the CLI.
