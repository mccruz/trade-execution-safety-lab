# Connector conformance contract

## Why this layer exists

Official broker and exchange SDKs solve transport concerns such as request
signing, HTTP serialization, and vendor endpoint coverage. They do not guarantee
that an automation system interprets every order, fill, position, retry, or
restart safely.

This project adds a provider-neutral conformance layer above an official SDK.
The layer is reusable across future paper or testnet adapters and deliberately
separate from strategy logic.

| Official SDK responsibility | Safety-lab responsibility |
| --- | --- |
| Authenticate a request | Keep credentials out of models, logs, fixtures, and receipts |
| Call a provider endpoint | Restrict which environment and product mode are constructible |
| Return provider payloads | Normalize values into decimal-safe provider-neutral models |
| Surface provider errors | Map them to redacted, typed failure categories |
| Expose order and position APIs | Validate identifiers, fills, transitions, pagination, and reconciliation |

## Venue contract

An `ExecutionVenue` declares:

- A non-secret safety profile: provider, environment, network permission,
  credential requirement, and live-trading permission.
- Whether a network-capable method has been invoked.
- Submit, poll, cancel, lookup-by-client-ID, and position-snapshot operations.

The engine accepts no live-enabled profile. The supplied profiles are the
network-disabled simulator and the fixed Bybit Testnet adapter.

## Checked invariants

The engine automatically wraps a venue in `ConformingVenue`, which validates
normalized data before orchestration consumes it:

- Order identifiers and immutable order fields remain stable.
- A recovered order matches the current client intent.
- Requested and filled quantities are finite and positive where required.
- Fill fees remain finite and signed, preserving both expenses and rebates.
- Fill identifiers and sequence numbers are unique and monotonic.
- Fills cannot exceed the requested quantity.
- Filled and partially-filled statuses agree with observed quantities.
- Previously observed fills cannot disappear or change.
- Terminal order status cannot transition again.
- Position snapshots normalize to at most one entry per symbol.

Any violation becomes a non-retryable protocol error. The engine records a
fail-closed outcome rather than guessing what the provider meant.

## Adapter-specific checks

Provider adapters remain responsible for checks that cannot be expressed
generically. The Bybit Testnet adapter additionally verifies:

- The SDK client exposes only `https://api-testnet.bybit.com`.
- Category is `linear`, submitted `positionIdx` is `0`, and hedge-mode data is
  rejected.
- Instrument constraints are loaded from Testnet before submission.
- Client order IDs meet the provider's length boundary.
- Execution history agrees with cumulative and remaining order quantities.
- Execution records belong to the requested venue order.
- Pagination terminates within a configured bound and cursors do not repeat.
- Provider error text is not copied into public exceptions or receipts.

## Deterministic verification

The adapter accepts an injected SDK client. Tests provide a deterministic fake
with the same method surface, allowing malformed responses, authentication
failures, rate limits, pagination loops, fill mismatches, and order transitions
to be exercised without a secret or network connection.

This is intentionally a contract test, not a claim that Testnet and mainnet are
identical. An authenticated smoke test is a separate manual activity and is not
run in public CI.

## Adding another connector

A future paper or testnet connector should:

1. Use the provider's official, redistributable SDK where practical.
2. Define a fixed non-live safety profile.
3. Keep its dependency optional so the offline demo remains minimal.
4. Normalize through the existing models and wrap with `ConformingVenue`.
5. Provide credential-free deterministic contract tests.
6. Document supported products, account modes, error mapping, and omissions.
7. Complete dependency-license, security, privacy, and clean-install review.
8. Receive separate approval before publication.

Mainnet, production deployment, embedded credentials, private strategy logic,
and automatic environment switching remain outside this repository.
