# Contributing

Contributions should preserve the offline-first, deterministic, fail-closed
boundary.

## Local checks

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps .
python -m unittest discover -s tests -v
python -m compileall -q src tests
trade-safety-lab demo --output-dir demo-output --reset
```

## Requirements

- Keep demos synthetic. Connector contract fixtures may use identifiers from
  public provider documentation, but never real account, order, position, or
  strategy data.
- Add a deterministic test for every new state transition or safety decision.
- Keep monetary arithmetic in `Decimal`.
- Do not add strategy logic, credentials, private data, performance claims, or
  operational configuration.
- Keep the default package, demo, and CI free of network access and credentials.
- Put optional provider dependencies behind a named extra and pin the reviewed
  version.
- Connector tests must use injected fakes and cover malformed responses,
  inconsistent state, error redaction, environment restrictions, and bounded
  pagination.
- Never add a mainnet or live-trading construction path.
- New providers or dependency changes require a separately scoped release,
  dependency-license review, security review, and explicit approval.
- Update README evidence counts when tests change.
