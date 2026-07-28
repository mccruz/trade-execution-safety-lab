# Trade Execution Safety Lab

Trade Execution Safety Lab is an offline Python case study for reliable broker and
exchange automation. It demonstrates guarded order submission, cancellation-race
handling, partial-fill accounting, position reconciliation, restart recovery, and
tamper-evident evidence—without a trading strategy, live account, credentials, or
network access.

![Architecture of the offline trade execution safety workflow](assets/architecture.svg)

## Three-minute recruiter review — no setup required

This project is designed to be understandable before anyone runs code:

1. Scan the [eight failure and recovery scenarios](docs/scenarios.md).
2. Follow the [execution and evidence architecture](docs/architecture.md).
3. Review the fail-closed orchestration in
   [`engine.py`](src/trade_execution_safety_lab/engine.py) and the deterministic
   venue in [`simulator.py`](src/trade_execution_safety_lab/simulator.py).
4. See how the [88 unit tests](tests/) cover business-critical edge cases.

The key outcome is not a trading result. It is evidence that an automated system
can refuse unsafe work, recognize uncertain order state, reconcile against the
venue, and route exceptions to a human.

## What the implementation proves

| Reliability problem | Implemented control | Evidence |
| --- | --- | --- |
| Invalid price, quantity, or minimum order | Decimal-safe pre-submission validation | `invalid-minimum` |
| Stale local position state | Venue-as-source-of-truth preflight reconciliation | `position-drift` |
| Duplicate submission after restart | Client-order idempotency plus verified receipt recovery | Restart evidence in `summary.json` |
| Partial fills | Weighted fills, fees, exposure update, and manual deferral | `partial-fill-cancel` |
| Fill/cancel race | Final venue state wins over the cancellation request | `cancel-fill-race` |
| Cancellation never resolves | Bounded observation and fail-closed outcome | `unresolved-cancel` |
| Rejection or connection interruption | Typed outcomes with no automatic retry authorization | `rejected-order`, `transient-disconnect` |
| Evidence tampering | Canonical SHA-256 receipts written atomically | Receipt verification tests |

## Safety boundary

Version 1.0 is a simulator-only engineering lab:

- No broker or exchange SDK is installed.
- No HTTP, WebSocket, or other network client exists.
- No API key, account identifier, environment-variable credential, or endpoint is
  accepted.
- `DEMO-USD` and every order, fill, fee, position, and error are synthetic.
- The alternating toy signal uses only a fixture index; it contains no economic
  or strategy logic.
- Only a fully filled, postflight-reconciled synthetic order authorizes the demo
  workflow to continue. All uncertain states stop.

Real paper-account or testnet adapters, if added later, will be isolated,
opt-in, disabled in CI, and released only after a separate security, licensing,
and privacy review.

## Run the offline demo

### 1. Open the repository directory

If you downloaded the ZIP, unzip it and open Terminal in that folder. If you use
Git:

```bash
git clone https://github.com/mccruz/trade-execution-safety-lab.git
cd trade-execution-safety-lab
```

The remaining commands must be run from the repository directory—the folder
containing this README and `pyproject.toml`.

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

The suite currently contains 88 tests. GitHub Actions repeats the tests on
Python 3.11, 3.12, 3.13, and 3.14 and runs the complete offline demo separately.

## Explore one scenario

```bash
trade-safety-lab list-scenarios
trade-safety-lab demo --output-dir demo-output --reset --scenario cancel-fill-race
```

If `demo-output` already contains lab evidence, `--reset` removes it only when
the directory has the lab-owned sentinel. The CLI refuses broad paths,
symbolic-link targets, and non-lab directories.

## Architecture and design notes

- [Architecture and safety invariants](docs/architecture.md)
- [Scenario catalog and expected decisions](docs/scenarios.md)
- [Authorship, provenance, and privacy boundary](docs/provenance.md)
- [Security policy](SECURITY.md)
- [Contribution guide](CONTRIBUTING.md)

The adapter is a Python
[`Protocol`](src/trade_execution_safety_lab/adapters.py), so orchestration depends
on a small provider-neutral contract. Version 1.0 supplies only
[`SimulatedVenue`](src/trade_execution_safety_lab/simulator.py). That distinction
is intentional: a simulator is executable adapter code for deterministic
failure testing, not a live connector with credentials removed.

## Limitations

- This is not financial advice, a strategy, a backtest, or a production trading
  system.
- The simulator models selected execution-control risks, not every venue rule,
  order type, latency condition, or market microstructure behavior.
- Receipts demonstrate local integrity and atomic persistence; they are not
  externally signed or independently timestamped.
- Recovery plans classify failures but do not sleep, reconnect, or access a
  network.
- No performance, profitability, or live-money claim is made.

## License

Code and original documentation are available under the [MIT License](LICENSE).
The project was newly written as a clean-history public derivative; private
trading repositories, histories, configurations, data, research, strategies,
and operational details are excluded. See [provenance](docs/provenance.md).
