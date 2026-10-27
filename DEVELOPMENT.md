# Development Guide

Local setup for the VigilRAI community edition. This tree is one organization. Do not add company registration or an organization header. To run the full stack in containers, use [Deploy with Docker](docs/deployment/docker.md). The shortest path, including the examples, is the [README](README.md).

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 22+ and pnpm 9+
- Docker and Docker Compose (PostgreSQL, Redis, or the full stack)

## Run locally

1. Copy the environment file.

   Windows (PowerShell): `Copy-Item .env.example .env`

   macOS or Linux: `cp .env.example .env`

2. Start PostgreSQL and Redis.

   ```bash
   docker compose up postgres redis -d
   ```

3. Install dependencies and apply migrations.

   Windows:

   ```powershell
   uv sync
   uv run alembic upgrade head
   ```

   macOS or Linux: `make setup` then `make migrate`.

4. Start the API on port 8001 so it matches the UI default.

   ```bash
   uv run uvicorn rai_gateway.main:app --reload --app-dir src --port 8001
   ```

5. In another terminal, start the console.

   ```bash
   pnpm --dir control-plane-ui install
   pnpm --dir control-plane-ui dev
   ```

6. Open http://localhost:3000 and sign in as `admin@raigateway.local` / `ChangeMe123!`.

7. Optional: run the lab examples from the [developer lab readme](examples/developer_lab/README.md).

`make dev` runs the API and UI in Compose with reload. `DATABASE_URL` in `.env` must point at `localhost:5434` when the API runs on the host.

## Unified Commands (`Makefile`)

| Command | Purpose |
|---------|---------|
| `make setup` | Install backend (uv) and frontend (pnpm) dependencies |
| `make dev` | Docker Compose with hot-reload (API `--reload`, UI `next dev`) |
| `make up` | Production-style Compose (UI image builds then runs `next start`) |
| `make lint` | Ruff + ESLint |
| `make format` | Ruff format + Prettier |
| `make format-check` | Check formatting without writes |
| `make typecheck` | mypy + TypeScript |
| `make test` | Backend unit + integration tests |
| `make test-unit` | Backend unit/API/architecture + Vitest |
| `make test-integration` | Backend integration tests (requires PostgreSQL) |
| `make test-e2e` | Backend e2e + Playwright smoke |
| `make migrate` | `alembic upgrade head` |
| `make migration-check` | Migration upgrade/downgrade tests |
| `make build` | Docker images + Next.js production build |
| `make security` | pip-audit + pnpm audit |
| `make ci` | Full local CI gate sequence |

## Database Migrations

Schema is owned exclusively by Alembic. Application startup does **not** call `create_all()`.

```bash
make migrate
uv run alembic revision --autogenerate -m "describe_change"
uv run alembic upgrade head
```

Set `DATABASE_URL` or `TEST_DATABASE_URL` for non-default PostgreSQL targets.

## Testing

Backend tests require PostgreSQL. Default test URL:

```text
postgresql://rai_user:rai_password@localhost:5434/rai_gateway
```

Override with `TEST_DATABASE_URL`. Tests use isolated schemas and Alembic migrations.

```bash
export TEST_DATABASE_URL=postgresql://rai_user:rai_password@localhost:5434/rai_gateway
make test
```

Frontend:

```bash
pnpm --dir control-plane-ui test:unit
pnpm --dir control-plane-ui build
pnpm --dir control-plane-ui test:e2e
```

## Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness (process alive) |
| `GET /ready` | Readiness (PostgreSQL connectivity) |
| `GET /version` | Build/version metadata (non-sensitive) |

## CI

GitHub Actions workflow: `.github/workflows/ci.yml`

Every PR runs backend lint/format/typecheck, PostgreSQL migration tests, full pytest suite, frontend lint/format/typecheck/build, Vitest, Playwright smoke, and security scans.

## Branch Protection (operational evidence required)

An administrator must enable on `main`:

- Require pull requests before merge
- Require status checks from CI jobs
- Block force pushes and branch deletion
- Require review for architecture/security-sensitive changes

## Troubleshooting

**PostgreSQL connection refused:** Start `docker compose up postgres -d` or set `TEST_DATABASE_URL` to a reachable instance.

**Alembic URL errors with `%`:** Use `DATABASE_URL` without manual URL-encoding in shell; test fixtures handle schema isolation.

**Port 5434 in use:** Compose publishes PostgreSQL on host port `5434`. Edit `docker-compose.yml` or point `DATABASE_URL` at another instance.

**First login:** `admin@raigateway.local` / `ChangeMe123!` when bootstrap is enabled. See `.env.example`.
