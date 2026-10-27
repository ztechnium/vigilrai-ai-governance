# Deploy with Docker

VigilRAI Community Edition is powered by [Ztechnium](https://ztechnium.com). Run it on one machine: API, console, PostgreSQL, and Redis. This is a single organization, not a multi-tenant service. It is the path for a first trial and for local integration. It is not a hardened production topology.

## Requirements

- Docker Engine and Docker Compose v2
- A copy of this repository

## First run

From the repository root:

```bash
cp .env.example .env
docker compose up --build
```

Compose publishes:

| Service | Host address | Notes |
|---|---|---|
| UI | http://localhost:3000 | Next.js production build (`next start`) |
| API | http://localhost:8001 | Container listens on port 8000 |
| PostgreSQL | `localhost:5434` | User `rai_user`, password `rai_password`, database `rai_gateway` |
| Redis | `localhost:6380` | No authentication in this Compose file |

The API container runs `alembic upgrade head` before Uvicorn. Startup does not load sample policies, prompts, or customer records.

### Sign in

The development defaults in `.env.example` and `docker-compose.yml` create one operator if none exists:

- Email: `admin@raigateway.local`
- Password: `ChangeMe123!`

Open http://localhost:3000 and sign in.

These passwords and the database password are for a private workstation. Replace them before anyone else can reach the host. There is no company registration page.

### Check the process

```bash
curl -fsS http://localhost:8001/health
curl -fsS http://localhost:8001/ready
curl -fsS http://localhost:8001/version
```

`/health` means the process is up. `/ready` means PostgreSQL answered.

## Develop against the containers

`make dev` uses `docker-compose.dev.yml`. The API reloads Python from `./src`, and the UI runs `next dev` instead of a production image.

```bash
cp .env.example .env
make dev
```

Run only the data stores and the API on the host when you want a debugger:

```bash
docker compose up postgres redis -d
make migrate
uv run uvicorn rai_gateway.main:app --reload --app-dir src --port 8001
pnpm --dir control-plane-ui dev
```

`make migrate` uses the `DATABASE_URL` in `.env`, which points at `localhost:5434`.

## Optional data

| Command | Effect |
|---|---|
| `make seed-mcp-catalog` | Loads `data/mcp_seed_catalog.json` (sample MCP templates). Idempotent. |
| `ENABLE_REFERENCE_PILOT_SEED=true` | Allows `POST /v1/governance/seed-reference-pilots` to add sample systems on this instance. Default is off, so the route responds 404. It does not create another organization. |

Leave both off for a clean trial.

## Production checklist

Do not publish the Compose defaults on a shared network.

1. Set `ENVIRONMENT=production`.
2. Generate new values for `JWT_SECRET_KEY` and `EVIDENCE_ENCRYPTION_KEY`.
3. Set `ADMIN_BOOTSTRAP_ENABLED=false` after the first operator exists, or set a unique `ADMIN_BOOTSTRAP_PASSWORD` before the first boot and then disable bootstrap.
4. Set `ADMIN_TOKEN` and `STEP_UP_TOKEN` to long random values. The UI image receives `NEXT_PUBLIC_ADMIN_TOKEN` at build time; do not bake a production admin token into a client bundle.
5. Set `CORS_ALLOWED_ORIGINS` to the real UI origin. Do not use `*` with credentials.
6. Set `APP_PUBLIC_URL` to the public UI URL.
7. Put PostgreSQL and Redis on private networks with credentials that are not the Compose examples.
8. Turn off demo-only switches: `ENABLE_REFERENCE_PILOT_SEED=false`, `EVIDENCE_USE_DEMO_CONTENT_DEFAULTS=false`, `MCP_ADAPTER_MODE=PRODUCTION`, `MCP_ALLOW_PRIVATE_HOSTS=false`, `MCP_ALLOW_HTTP=false`.

Copy `.env.example` for the full variable list. Backups are described in [Backup, restore, and disaster recovery](../operations/BACKUP_RESTORE_DR.md).

## Build the images alone

```bash
docker compose build
docker build -t rai-gateway:local .
docker build -t rai-control-plane-ui:local ./control-plane-ui
```

The API image runs as a non-root user and includes Alembic plus the optional MCP catalog script. It does not include the deleted demo seeders.
