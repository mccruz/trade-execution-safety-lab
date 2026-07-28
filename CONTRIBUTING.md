# Contributing

Contributions should preserve the offline, deterministic, fail-closed boundary.

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

- Use only synthetic instruments, orders, fills, positions, errors, and outputs.
- Add a deterministic test for every new state transition or safety decision.
- Keep monetary arithmetic in `Decimal`.
- Do not add strategy logic, real symbols, credentials, endpoints, private data,
  performance claims, or operational configuration.
- Do not add a network dependency or live connector in a routine pull request.
  Those require a separately scoped release, dependency-license review, security
  review, and explicit approval.
- Update README evidence counts when tests change.
