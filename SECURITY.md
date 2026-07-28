# Security policy

## Scope

Version 1.0 is an offline simulator. It has no network client, credential input,
live connector, or production deployment path.

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

## Not supported

Do not use this repository to place a real order. Broker, exchange, paper,
testnet, market-data, notification, and live-trading integrations are not part of
version 1.0.
