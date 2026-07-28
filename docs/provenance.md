# Authorship, provenance, and privacy boundary

## Clean-history derivative

Trade Execution Safety Lab was newly written as a provider-neutral, synthetic
case study. It is informed by general reliability problems encountered in
independently owned private automation work, but it does not inherit any private
repository history or copy a private bot, strategy, configuration, or venue
integration.

The public implementation uses a separately chosen MIT license. Private source
repositories without public redistribution licenses remain private.

## Excluded material

The repository intentionally excludes:

- Strategy entry and exit logic, indicators, parameters, instruments, sizing,
  risk limits, and promotion decisions.
- Account identifiers, credentials, endpoints, gateway distributions,
  certificates, keystores, and authentication conventions.
- Production services, hosts, paths, schedules, notification routes, deployment
  topology, and recovery procedures.
- Market data, databases, logs, order history, performance results, P&L,
  backtests, research notebooks, and experiment artifacts.
- Vendor-restricted source, including VectorBT Pro trees.
- Original Git histories and dirty working-tree snapshots.

`DEMO-USD`, client order IDs, fills, fees, positions, errors, and outputs in this
repository are fictional.

## Candidate concepts reviewed

The clean-room design considered only generic concepts for ownership review:
normalized order results, idempotency, position reconciliation, guarded
submission, cancellation races, partial fills, bounded recovery, tick and
minimum-order validation, weighted fills, and provider-neutral connection
classification.

An untracked private WebSocket helper was explicitly excluded. No private
candidate file is a publication source snapshot.

## Future connectors

A later paper-account or testnet connector may use independently owned
integration code when its SDK license permits redistribution. Such work must be
isolated, opt-in, disabled in CI, environment-configured without values, blocked
from live trading by default, and independently reviewed before release.

Version 1.0 has no connector configuration surface and no network dependency.
