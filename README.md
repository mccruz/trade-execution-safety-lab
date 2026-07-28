# Trade Execution Safety Lab

Trade Execution Safety Lab is an offline-first Python case study for reliable
broker and exchange automation. It combines a deterministic failure simulator,
a reusable adapter-conformance layer, and an optional Bybit Testnet reference
adapter built on the official SDK.

The project demonstrates guarded order submission, cancellation-race handling,
partial-fill accounting, position reconciliation, restart recovery, and
tamper-evident evidence. It contains no trading strategy, production
configuration, live account details, performance claims, or mainnet path.

![Architecture of the offline-first trade execution safety workflow](assets/architecture.svg)

## Three-minute recruiter review — no setup required

No account, installation, or technical background is needed for this review:

1. Scan the [eight plain-language failure and recovery scenarios](docs/scenarios.md).
2. Follow the [execution and evidence architecture](docs/architecture.md).
3. Compare the [provider-neutral conformance controls](docs/connector-conformance.md)
   with the [Bybit Testnet adapter boundary](docs/connectors/bybit-testnet.md).
4. See how the [128 unit tests](tests/) cover business-critical edge cases.

The outcome is not a trading result. It is evidence that an automated system can
refuse unsafe work, detect inconsistent provider data, reconcile against a
source of truth, and route uncertainty to a human.

## What the implementation proves

| Reliability problem | Implemented control | Evidence |
| --- | --- | --- |
| Invalid price, quantity, or minimum order | Decimal-safe pre-submission validation | `invalid-minimum` |
| Stale local position state | Venue-as-source-of-truth preflight reconciliation | `position-drift` |
| Duplicate submission after restart | Client-order idempotency plus verified receipt recovery | Restart evidence in `summary.json` |
| Partial fills | Weighted fills, fees, exposure update, and manual deferral | `partial-fill-cancel` |
| Fill/cancel race | Final venue state wins over the cancellation request | `cancel-fill-race` |
| Cancellation never resolves | Bounded observation and fail-closed outcome | `unresolved-cancel` |
| Malformed or contradictory provider data | Reusable snapshot and transition conformance checks | Adapter contract tests |
| Wrong environment or account mode | Fixed Testnet endpoint and one-way-position enforcement | Bybit boundary tests |
| Rejection, rate limit, or interruption | Typed, redacted errors with no adapter-level retry | Error-mapping tests |
| Evidence tampering | Canonical SHA-256 receipts written atomically | Receipt verification tests |

## Two deliberately separate modes

### Default: offline simulator

- Built in, credential-free, and network-disabled.
- Uses only fictional `DEMO-USD` orders, fills, positions, fees, and errors.
- Runs the full recruiter demo and every CI check.
- Contains a deliberately non-economic toy signal and no strategy logic.

### Optional: Bybit Testnet reference adapter

- Uses the official
  [`pybit` 5.17.0 package](https://pypi.org/project/pybit/5.17.0/) as the
  transport SDK; it does not reimplement Bybit authentication or HTTP.
- Adds a safety layer the SDK does not provide: provider-neutral models,
  bounded pagination, idempotency checks, state-transition validation,
  reconciliation, typed evidence, and human-review outcomes.
- Accepts only the fixed Bybit Testnet endpoint, linear products, and one-way
  position mode. There is no mainnet endpoint option or live-trading profile.
- Reads optional Testnet credentials from two named environment variables.
  Real values are never committed or included in exceptions or receipts; tests
  use explicit non-secret placeholders.
- Is contract-tested with an injected fake SDK client. CI never contacts Bybit
  and never needs a secret.

This is actual adapter code, not a placeholder with keys removed. It is also
intentionally not a turnkey trading bot: the repository supplies no strategy,
live command, production deployment, or automatic mainnet switch.

Inspect the boundaries without installing the optional SDK:

```bash
trade-safety-lab list-connectors
```

## Run the offline demo

### 1. Open the repository directory

If you downloaded the ZIP, unzip it and open Terminal in that folder. If you use
Git:

```bash
git clone https://github.com/mccruz/trade-execution-safety-lab.git
cd trade-execution-safety-lab
```

The remaining commands must be run from the folder containing this README and
`pyproject.toml`.

### 2. Create an isolated Python environment

Python 3.11 or newer is required. A virtual environment avoids macOS Homebrew's
`externally-managed-environment` error and does not modify system Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps .
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.
The regular local install intentionally avoids editable-install path files that
newer macOS Python versions may treat as hidden.

### 3. Run all eight scenarios

```bash
trade-safety-lab demo --output-dir demo-output --reset
```

Success looks like:

```text
Offline demo passed: 8 scenario(s), no network, no credentials.
Evidence: .../demo-output/summary.md
```

Open `demo-output/summary.md` for the readable report. Each JSON receipt in
`demo-output/receipts/` contains its own SHA-256 digest. Verify one with:

```bash
trade-safety-lab verify-receipt demo-output/receipts/DEMO-FULL-FILL.json
```

No Docker, database, external service, account, or authentication key is needed.

## Run the tests

With the virtual environment active:

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

The suite contains 128 tests. GitHub Actions repeats them on Python 3.11, 3.12,
3.13, and 3.14 and runs the complete offline demo separately. The default jobs
import the optional connector without installing `pybit`, proving that the base
package remains isolated. A separate credential-free job installs the pinned
SDK and checks its Testnet endpoint without sending a provider request.

## Explore the lab

```bash
trade-safety-lab list-scenarios
trade-safety-lab list-connectors
trade-safety-lab demo --output-dir demo-output --reset --scenario cancel-fill-race
```

If `demo-output` already contains lab evidence, `--reset` removes it only when
the directory has the lab-owned sentinel. The CLI refuses broad paths,
symbolic-link targets, and non-lab directories.

Technical reviewers can install the optional connector dependencies with:

```bash
python -m pip install '.[bybit-testnet]'
```

Installation does not contact Bybit or place an order. Continue with the
[Bybit Testnet setup and review guide](docs/connectors/bybit-testnet.md) before
constructing the connector.

## Architecture and design notes

- [Architecture and safety invariants](docs/architecture.md)
- [Connector conformance contract](docs/connector-conformance.md)
- [Bybit Testnet adapter review](docs/connectors/bybit-testnet.md)
- [Optional dependency and security review](docs/dependency-review.md)
- [Scenario catalog and expected decisions](docs/scenarios.md)
- [Authorship, provenance, and privacy boundary](docs/provenance.md)
- [Security policy](SECURITY.md)
- [Contribution guide](CONTRIBUTING.md)

The venue boundary is a small Python
[`Protocol`](src/trade_execution_safety_lab/adapters.py). The same orchestration
can therefore evaluate the deterministic simulator or an explicitly enabled
Testnet adapter, while [`ConformingVenue`](src/trade_execution_safety_lab/conformance.py)
checks normalized data before the engine consumes it.

## Limitations

- This is not financial advice, a strategy, a backtest, or a production trading
  system.
- Testnet behavior does not prove production readiness and can differ from
  mainnet behavior.
- The authenticated Bybit path is not exercised in public CI. The adapter is
  verified through deterministic contract tests and optional-dependency checks.
- The simulator and reference adapter cover selected execution-control risks,
  not every venue rule, order type, latency condition, or market behavior.
- Receipts demonstrate local integrity and atomic persistence; they are not
  externally signed or independently timestamped.
- No performance, profitability, or live-money claim is made.

## License

Code and original documentation are available under the [MIT License](LICENSE).
The project was newly written as a clean-history public derivative; private
trading repositories, histories, configurations, data, research, strategies,
parameters, and operational details are excluded. See
[provenance](docs/provenance.md).
