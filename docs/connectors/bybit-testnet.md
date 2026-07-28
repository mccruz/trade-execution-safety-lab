# Bybit Testnet reference adapter

## Plain-language summary

This is real integration code for Bybit's public Testnet API, built on Bybit's
official Python SDK. It is not a copy of the SDK and does not try to improve the
vendor's authentication or endpoint coverage.

Its added value is the safety boundary around the SDK: fixed environment,
provider-neutral data, bounded calls, consistency checks, reconciliation,
redacted failures, and checksummed execution receipts.

Recruiters can review the implementation without an account:

- [`bybit_testnet.py`](../../src/trade_execution_safety_lab/connectors/bybit_testnet.py)
- [`test_bybit_testnet.py`](../../tests/test_bybit_testnet.py)
- [Connector conformance contract](../connector-conformance.md)

## Supported boundary

| Area | Included |
| --- | --- |
| Provider | Bybit |
| Environment | Testnet only |
| Endpoint | Fixed `https://api-testnet.bybit.com` |
| SDK | Official `pybit==5.17.0` optional dependency |
| Product category | Linear |
| Position mode | One-way (`positionIdx=0`) |
| Order types | Limit and market intents |
| Operations | Instrument rules, positions, lookup, submit, poll, executions, cancel |
| Evidence | Safety profile, network-use flag, typed outcome, SHA-256 receipt |

There is no mainnet endpoint option, demo-trading switch, hedge-mode support,
WebSocket stream, strategy, scheduler, deployment service, or live-order CLI.

## Review without credentials

The normal installation remains dependency-free:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps .
trade-safety-lab list-connectors
python -m unittest discover -s tests -v
```

These commands do not contact Bybit. The default public CI jobs follow the same
credential-free path and use an injected fake SDK client for connector tests. A
separate job installs the pinned SDK and verifies its constructed Testnet
endpoint without sending a provider request.

## Optional SDK installation

Technical reviewers can install the pinned official SDK extra:

```bash
python -m pip install '.[bybit-testnet]'
```

The pin makes the reviewed transport version explicit. The package is sourced
from the
[`pybit` 5.17.0 PyPI release](https://pypi.org/project/pybit/5.17.0/),
published from the
[`bybit-exchange/pybit` repository](https://github.com/bybit-exchange/pybit).

## Credential handling

Only dedicated Testnet credentials should ever be used. The adapter reads these
two environment-variable names:

```text
BYBIT_TESTNET_API_KEY
BYBIT_TESTNET_API_SECRET
```

The checked-in [`.env.example`](../../.env.example) contains empty values only.
The project does not automatically load `.env` files, real values are ignored by
Git, and real credential values are not included in adapter representations,
exceptions, models, fixtures, or receipts. Tests use clearly labeled non-secret
placeholders.

After setting values outside the repository, construction is explicit:

```python
from trade_execution_safety_lab import ConformingVenue
from trade_execution_safety_lab.connectors import BybitTestnetVenue

venue = ConformingVenue(BybitTestnetVenue.from_environment())
```

This guide intentionally does not provide a turnkey order command. Any
authenticated Testnet exercise should use a dedicated account, minimal
permissions, independently reviewed order intent, and human observation.

## Fail-closed behavior

- Instrument rules are fetched before submission and must exactly match the
  intent's constraints.
- Client IDs are bounded and used for duplicate-order recovery.
- SDK retries are disabled, including its provider-code retry set; the adapter
  makes one bounded call and returns a typed result to the orchestration layer.
- Authentication and protocol failures do not authorize retries.
- Rate limits and transport failures are classified as retryable information,
  but the adapter itself does not retry an unconfirmed submission.
- Only regular linear order statuses are normalized; conditional and spot-only
  statuses remain unknown, and unsupported execution types fail closed.
- Signed execution fees are preserved so a provider-reported rebate is not
  silently converted or rejected.
- Order/execution quantity disagreement, repeated pagination cursors, duplicate
  identifiers, and hedge-mode responses stop processing.
- The conformance wrapper rejects regressing fills or status transitions.

## Verification status

- The connector and conformance paths are covered by deterministic unit and
  integration-style contract tests.
- The pinned official SDK is included only in the optional install and is
  validated through a clean dependency installation.
- No credential is stored in the repository.
- No authenticated request or Testnet order is made by CI or release validation.
- No mainnet or profitability claim is made.

## Official references

- [Bybit V5 integration guide](https://bybit-exchange.github.io/docs/v5/guide)
- [Create order](https://bybit-exchange.github.io/docs/v5/order/create-order)
- [Open and closed orders](https://bybit-exchange.github.io/docs/v5/order/open-order)
- [Order history](https://bybit-exchange.github.io/docs/v5/order/order-list)
- [Execution list](https://bybit-exchange.github.io/docs/v5/order/execution)
- [Position information](https://bybit-exchange.github.io/docs/v5/position)
- [Order-status enums](https://bybit-exchange.github.io/docs/v5/enum)
