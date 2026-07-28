# Authorship, provenance, and privacy boundary

## Clean-history derivative

Trade Execution Safety Lab was newly written as a provider-neutral, synthetic
case study. It is informed by general reliability problems encountered in
independently owned private automation work, but it does not inherit any private
repository history or copy a private bot, strategy, configuration, or private
venue integration.

The public implementation uses a separately chosen MIT license. Private source
repositories without public redistribution licenses remain private.

## Excluded material

The repository intentionally excludes:

- Strategy entry and exit logic, indicators, parameters, instruments, sizing,
  risk limits, and promotion decisions.
- Account identifiers, credentials, private or production endpoints, gateway
  distributions, certificates, keystores, and authentication conventions.
- Production services, hosts, paths, schedules, notification routes, deployment
  topology, and recovery procedures.
- Market data, databases, logs, order history, performance results, P&L,
  backtests, research notebooks, and experiment artifacts.
- Vendor-restricted source, including VectorBT Pro trees.
- Original Git histories and dirty working-tree snapshots.

The simulator's `DEMO-USD` instrument, client order IDs, fills, fees, positions,
errors, and outputs are fictional. Connector contract fixtures use public sample
symbols and clearly non-real identifiers; they contain no account-derived data.

## Candidate concepts reviewed

The clean-room design considered only generic concepts for ownership review:
normalized order results, idempotency, position reconciliation, guarded
submission, cancellation races, partial fills, bounded recovery, tick and
minimum-order validation, weighted fills, and provider-neutral connection
classification.

An untracked private WebSocket helper was explicitly excluded. No private
candidate file is a publication source snapshot.

## Version 1.1 connector provenance

The Bybit Testnet adapter is newly written against publicly documented V5 API
semantics. It uses the official
[`pybit` 5.17.0](https://pypi.org/project/pybit/5.17.0/) package as an optional
dependency under its MIT license. No SDK source is copied or vendored.

PyPI identifies the package as published from
[`bybit-exchange/pybit`](https://github.com/bybit-exchange/pybit) at tag
`v5.17.0`, source commit
`fdab314ec1e9d7ad6127aaa1721f24557d6705ee`, using trusted publishing. The
adapter behavior is based on Bybit's public
[V5 documentation](https://bybit-exchange.github.io/docs/v5/guide).

The clean-install versions, reported licenses, vulnerability scan, and secret
scan are recorded in the
[optional dependency review](dependency-review.md).

The repository includes only the public Testnet endpoint and environment
variable names with empty example values. It includes no account, credential,
private order, strategy, research, or operational detail.

## Future connectors

Any additional paper or testnet connector must remain isolated, opt-in,
credential-free in CI, environment-configured without values, blocked from live
trading, and independently reviewed for SDK licensing, security, and privacy
before release.
