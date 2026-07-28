# Security policy

## Scope

The default demo is an offline simulator with no network client or credential
input. Version 1.1 adds an isolated, optional Bybit Testnet adapter backed by the
official `pybit` SDK.

The Testnet adapter has no mainnet endpoint option, live-trading profile,
production deployment path, embedded key, or automatic environment switch.

Please report a vulnerability privately through GitHub's security-advisory
feature after publication. Do not include real account details, credentials,
private order data, or production logs in a public issue.

## Expected safety properties

- Validation and reconciliation can block submission.
- Client order identifiers suppress duplicate submissions.
- Uncertain order or cancellation state fails closed.
- Generated receipts verify before restart recovery.
- Output reset is limited to a sentinel-marked lab directory.
- CI uses synthetic data and requires no secrets.
- Normalized order and position data must satisfy the conformance contract.
- The Bybit adapter accepts only the fixed Testnet endpoint, linear category,
  and one-way position mode.
- Provider exception text is discarded before a typed error is recorded.
- Optional credentials are read from named environment variables and are not
  serialized into models or receipts.

## Testnet credential guidance

Testnet credentials are still secrets:

- Never use a production or mainnet key with this project.
- Do not put real values in `.env.example`, source, fixtures, issues, receipts,
  screenshots, or logs.
- Use a dedicated Testnet key with the minimum permissions needed for a
  separately reviewed exercise.
- Rotate or delete a key immediately if it is exposed.
- Public CI and release validation must remain credential-free.

The repository does not automatically load `.env` files. Local `.env` variants
are ignored by Git as a defense-in-depth measure.

## Dependency boundary

The default package has no runtime dependency. `pybit==5.17.0` and its
transitive dependencies are installed only through the `bybit-testnet` optional
extra. Dependency and license checks must be repeated before changing the pin.

The adapter does not copy provider exception messages into receipts because
upstream messages can contain request context. It also disables SDK request
logging and automatic request retries.

## Not supported

Do not use this repository for mainnet, live funds, production deployment, or
unattended trading. Paper connectors other than the documented Bybit Testnet
adapter, market-data pipelines, notification routes, and live-trading
integrations are not supported.

An authenticated Testnet smoke test is intentionally outside public CI and is
not required for the recruiter demo.
