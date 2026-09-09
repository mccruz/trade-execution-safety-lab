# Trade Execution Safety Lab

An offline Python lab for a concrete automation risk: a connection fails
after an order is sent, and a retry could duplicate the action. The lab checks
order and recovery behavior using a simulated provider and fictional orders.

## Example result

**Synthetic demo results:**

| Situation | Result |
| --- | --- |
| Order fills while cancellation is in progress | Record the provider's final filled state |
| Cancellation remains unresolved | Defer the unknown outcome for review |
| Local and provider positions disagree | Block until reconciled |

The offline demo generates a readable report for eight scenarios. Separate
[restart tests](tests/test_receipts_restart.py) check recovery of an existing
order rather than duplicate submission. These results establish selected
engineering behavior, not profitability or production readiness.

## My contribution

I implemented the order checks, provider contract, simulated failure scenarios,
restart handling, and checksummed receipts. The default lab uses no LLM, market
data, account credentials, or trading strategy.

![Architecture of the offline trade execution safety workflow](assets/architecture.svg)

<a id="review-this-project-in-3-minutes"></a>

## Explore the project

Start with the example above, then follow the diagram and the
[engineering evidence](#engineering-evidence). Setup is optional for review.

## How it works

1. Validate an order before it can be submitted.
2. Compare the local position with the simulated provider's position.
3. Submit with a stable identifier so a restart cannot create a duplicate.
4. Track fills, fees, cancellations, and provider responses.
5. Reconcile the final state after timeouts, races, or reconnects.
6. Write a verifiable receipt and require human review when the outcome remains
   uncertain.

## Failure scenarios

| Scenario | Expected behavior |
| --- | --- |
| Invalid order size | Reject it before submission |
| Position mismatch | Pause and reconcile with the provider |
| Restart after submission | Recover the existing order instead of duplicating it |
| Partial fill | Record the fill and defer the unresolved remainder |
| Fill during cancellation | Accept the provider's final state as authoritative |
| Cancellation timeout | Stop after limited checks and report uncertainty |
| Bad provider response | Reject malformed or contradictory data |
| Rate limit or interruption | Return a clear error without hidden retries |

Receipts are written as complete files and include a SHA-256 digest so later
changes can be detected.

## Two separate modes

### Offline simulator

The default mode is built in, credential-free, and network-disabled. It uses
fictional `DEMO-USD` orders and runs every scenario used in CI. It contains no
economic strategy, market data, or performance claim.

### Optional Bybit Testnet adapter

The optional adapter shows how the same safety checks can wrap an external SDK.
It is fixed to Bybit Testnet, linear products, and one-way position mode. There
is no mainnet option, live deployment command, or automatic environment switch.

Public CI uses a fake injected client and never authenticates or sends an order.
The [Testnet adapter guide](docs/connectors/bybit-testnet.md) documents the exact
boundary and limitations.

## Engineering evidence

| Capability | Implementation | Check |
| --- | --- | --- |
| Handle fill/cancel uncertainty | [Engine](src/trade_execution_safety_lab/engine.py) | [Engine tests](tests/test_engine.py) |
| Recover without duplicating an order | [Restart](src/trade_execution_safety_lab/restart.py) | [Restart tests](tests/test_receipts_restart.py) |
| Reject conflicting provider state | [Reconciliation](src/trade_execution_safety_lab/reconciliation.py) | [Reconciliation tests](tests/test_reconciliation.py) |

## Optional offline demo

Python 3.11 or newer is required:

```bash
git clone https://github.com/mccruz/trade-execution-safety-lab.git
cd trade-execution-safety-lab
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps .
trade-safety-lab demo --output-dir demo-output --reset
```

A successful run reports eight completed scenarios with no network or
credentials. Open `demo-output/summary.md` for the readable report.

Useful review commands:

```bash
trade-safety-lab list-scenarios
trade-safety-lab list-connectors
trade-safety-lab verify-receipt demo-output/receipts/DEMO-FULL-FILL.json
```

The CLI removes old demo output only when it finds the lab's own marker. It
rejects broad paths, symbolic-link targets, and unrelated directories.

## Safety and limits

- The repository contains no trading strategy, production configuration, live
  account details, or profitability claims.
- The default demo cannot make network requests or place orders.
- Testnet behavior does not prove production readiness and can differ from
  mainnet.
- The authenticated Bybit path is not exercised in public CI.
- The simulator covers selected order and recovery risks, not every venue rule,
  order type, latency condition, or market behavior.
- Local receipt checks detect later file changes but are not externally signed
  or independently timestamped.

This project is an engineering demonstration, not financial advice, a backtest,
or a production trading system.

## Verification

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

GitHub Actions runs the full offline demo and tests across supported Python
versions. A separate credential-free check installs the optional SDK and
confirms its fixed Testnet configuration without contacting the provider.

## Project guide

- [Failure scenarios](docs/scenarios.md)
- [Architecture and safety rules](docs/architecture.md)
- [Provider adapter contract](docs/connector-conformance.md)
- [Bybit Testnet boundary](docs/connectors/bybit-testnet.md)
- [Dependency review](docs/dependency-review.md)
- [Security policy](SECURITY.md)
- [Public/private boundary](docs/provenance.md)

## License

Code and original documentation are available under the [MIT License](LICENSE).
Private trading systems, configurations, data, research, strategies, and
operational details are excluded from this clean public project.
