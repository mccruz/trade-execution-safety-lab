# Optional connector dependency review

Review date: 2026-07-28

## Scope

The default project has no runtime dependency. This review covers only the
optional `bybit-testnet` extra and was performed in a new Python 3.14 virtual
environment.

The reviewed direct dependency is `pybit==5.17.0`, Bybit's official Python SDK.
PyPI reports trusted publishing from the `bybit-exchange/pybit` `v5.17.0` tag
and source commit `fdab314ec1e9d7ad6127aaa1721f24557d6705ee`.

## Clean-install snapshot

| Package | Resolved version | Reported license |
| --- | --- | --- |
| `pybit` | 5.17.0 | MIT |
| `requests` | 2.34.2 | Apache-2.0 |
| `websocket-client` | 1.9.0 | Apache-2.0 |
| `pycryptodome` | 3.23.0 | BSD / Public Domain |
| `charset-normalizer` | 3.4.9 | MIT |
| `idna` | 3.18 | BSD-3-Clause |
| `urllib3` | 2.7.0 | MIT |
| `certifi` | 2026.7.22 | MPL-2.0 |

The package's direct SDK pin is fixed. Transitive versions are this validation
snapshot, not additional application-level pins; they can change when the
optional environment is created later.

## Checks performed

- Built and installed the project wheel with `.[bybit-testnet]`.
- Confirmed `pip check` reported no broken requirements.
- Confirmed the installed project and SDK versions were `1.1.0` and `5.17.0`.
- Constructed the official SDK client with the Testnet flags and verified its
  endpoint was exactly `https://api-testnet.bybit.com`.
- Ran all 128 credential-free tests and compiled `src` and `tests`.
- Ran `pip-audit 2.10.1` against the installed dependency directory; it reported
  no known vulnerabilities in the auditable packages.
- Scanned Git history and the working tree with checksummed Gitleaks 8.30.1; it
  reported no leaks.

The local project itself is not published on PyPI, so `pip-audit` correctly
reported it as unavailable to the package-index vulnerability query. Its source,
tests, dependency graph, and secret exposure were reviewed separately.

## Explicit omissions

- No real credential was set.
- No authenticated request was sent.
- No Testnet or mainnet order was placed.
- No production account, strategy, configuration, or operational data was used.

Re-run this review immediately before release and whenever the direct SDK pin or
resolved dependency set changes.

## Primary references

- [`pybit` 5.17.0 on PyPI](https://pypi.org/project/pybit/5.17.0/)
- [Official `bybit-exchange/pybit` repository](https://github.com/bybit-exchange/pybit)
- [Bybit V5 integration guide](https://bybit-exchange.github.io/docs/v5/guide)
- [Gitleaks repository and usage](https://github.com/gitleaks/gitleaks)
