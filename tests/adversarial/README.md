# Adversarial tests

This community edition is one instance. It does not ship a cross-organization isolation suite, because there is no second organization to isolate.

Authorization tests live in `tests/authorization` and `tests/auth`. They check that a caller without a membership is denied, and that a membership grants only the permissions mapped from that role.

Run them with PostgreSQL available:

```bash
uv run pytest tests/authorization tests/auth
```
