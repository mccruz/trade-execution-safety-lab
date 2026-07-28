# Changelog

## 1.1.0 — 2026-07-28

- Add reusable order, fill, transition, and position conformance checks.
- Add an optional Bybit Testnet reference adapter built on the official
  `pybit==5.17.0` SDK.
- Structurally restrict the adapter to the fixed Testnet endpoint, linear
  products, and one-way position mode; no mainnet construction path exists.
- Add redacted provider error mapping, bounded pagination, instrument-rule
  verification, signed fee/rebate accounting, execution-summary cross-checks,
  and dynamic network-use evidence.
- Add optional-connector documentation, empty credential-name examples, and
  recruiter-friendly comparison with the official SDK.
- Expand the credential-free suite to 128 tests while keeping the complete
  offline demo as the default CI path.

## 1.0.0 — 2026-07-28

- Add provider-neutral venue protocol and deterministic simulated venue.
- Add decimal-safe validation, fill accounting, position reconciliation, and
  bounded order/cancellation observation.
- Add fail-closed outcomes for partial fills, rejections, drift, disconnects,
  and unresolved cancellation.
- Add canonical checksummed receipts and restart duplicate-submission
  suppression.
- Add eight offline scenarios, 88 unit tests, multi-version CI, recruiter-first
  documentation, and publication metadata.
