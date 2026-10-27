# Contributing

Thanks for helping improve the VigilRAI community edition. The project is licensed under the Apache License 2.0. By submitting a contribution, you agree that your work is licensed under those terms.

This tree is a single-organization product. Do not add company registration, a public marketing site, an organization switcher, `X-Organization-ID`, or a second tenant key. People belong to the instance through memberships and departments. Platform roles stay separate and only authorize the admin console.

## Set up a local checkout

Follow [DEVELOPMENT.md](DEVELOPMENT.md). The short path is:

**Windows (PowerShell)**

```powershell
Copy-Item .env.example .env
docker compose up postgres redis -d
uv sync
uv run alembic upgrade head
uv run pytest
```

**macOS or Linux**

```bash
cp .env.example .env
make setup
docker compose up postgres redis -d
make migrate
make test
```

Python 3.12+, uv, Node.js 22+, and pnpm 9+ are required for the full suite. Docker is required for PostgreSQL and Redis.

Sign in at http://localhost:3000 with `admin@raigateway.local` / `ChangeMe123!` after the API is running. To try the bundled agents, follow the example steps in the [README](README.md).

## What to change

- Keep governance decisions on the server. Callers do not choose their own risk tier, approval state, or effective permissions.
- Fail closed when identity, policy, or approval state cannot be verified.
- Put schema changes in a new Alembic revision. Do not add a second schema loader.
- Do not add demo customers, transcripts, or jurisdiction dumps to the default startup path. Local credentials belong in `.env.example` and must be obviously unsafe for production.
- Do not commit `.env`, API keys, or real passwords.

## Checks before a pull request

```bash
make lint
make format-check
make typecheck
make migration-check
make test
```

On Windows, without `make`, run the same tools directly: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run alembic upgrade head`, and `uv run pytest`. Frontend checks use `pnpm --dir control-plane-ui lint` and `pnpm --dir control-plane-ui exec tsc --noEmit`. Describe how you tested the change in the pull request.

## Security issues

Report vulnerabilities using [SECURITY.md](SECURITY.md). Do not open a public issue for an unfixed security bug.

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
