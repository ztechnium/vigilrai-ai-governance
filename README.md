<p align="center">
  <img src="https://i.postimg.cc/bw44qfz4/d3a24c15-d593-4d0e-89ee-86d4264c00cf.png" alt="VigilRAI" width="160">
</p>

# VigilRAI Community Edition

Governance for one organization, powered by [Ztechnium](https://ztechnium.com). Register the AI systems that may run, decide who is accountable, enforce policy before a tool or model action proceeds, and keep evidence of those decisions.

This edition is a single instance. It is not a hosted multi-organization service. There is no public marketing site, no company signup, and no organization switcher. Sign in, invite teammates, and use the console.

This repository is an **alpha**. It is not certified, and it is not a compliance attestation. [Current status](docs/releases/SYSTEM_STATUS.md) describes what the code implements today.

## What you need

- Docker Desktop with Docker Compose, for the simplest run
- Or, for a local process: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22+, pnpm 9+, and Docker for PostgreSQL and Redis

## Run with Docker

From the repository root.

**Windows (PowerShell)**

```powershell
Copy-Item .env.example .env
docker compose up --build
```

**macOS or Linux**

```bash
cp .env.example .env
docker compose up --build
```

Wait until the API reports healthy. Then open the services:

| Service | URL |
|---|---|
| Sign-in page | http://localhost:3000 |
| API | http://localhost:8001 |
| Health | http://localhost:8001/health |
| PostgreSQL | `localhost:5434` (`rai_user` / `rai_password`) |
| Redis | `localhost:6380` |

### Sign in

Use the bootstrap account from `.env.example`:

- Email: `admin@raigateway.local`
- Password: `ChangeMe123!`

The first page is the login form. After sign-in you land on the dashboard or the in-app welcome. A fresh database has system roles, one governance profile, and that admin. It does not load sample policies or customer data.

Invite more people from **Team & roles**. There is no public registration page.

Change every `change-me` and `dev-only` secret before any shared deployment, and set `ADMIN_BOOTSTRAP_ENABLED=false`. Details are in [Deploy with Docker](docs/deployment/docker.md).

Stop the stack with `docker compose down` from this directory.

## Run the API and UI on your machine

Use this when you want hot reload. Docker still runs PostgreSQL and Redis.

**Windows (PowerShell)**

```powershell
Copy-Item .env.example .env
docker compose up postgres redis -d
uv sync
uv run alembic upgrade head
uv run uvicorn rai_gateway.main:app --reload --app-dir src --port 8001
```

In a second terminal:

```powershell
pnpm --dir control-plane-ui install
pnpm --dir control-plane-ui dev
```

**macOS or Linux**

```bash
cp .env.example .env
make setup
docker compose up postgres redis -d
make migrate
uv run uvicorn rai_gateway.main:app --reload --app-dir src --port 8001
pnpm --dir control-plane-ui dev
```

`make dev` starts the same stack in containers with reload. The command list is in [DEVELOPMENT.md](DEVELOPMENT.md).

Sign in at http://localhost:3000 with the same bootstrap account.

## Use the examples

The examples register catalog rows in the running API, then send tool calls through policy. A local tool process on port 8765 writes tickets, orders, and audit rows only when RAI allows the action.

1. Start the community edition and confirm http://localhost:8001/health returns healthy.
2. From the repository root, run Support AI. It starts the local tool process, signs in as the bootstrap admin, registers that system, and runs its cases.

**Windows (PowerShell)**

```powershell
$env:RAI_BASE_URL = "http://localhost:8001"
$env:RAI_ADMIN_EMAIL = "admin@raigateway.local"
$env:RAI_ADMIN_PASSWORD = "ChangeMe123!"
python examples/support_ai_reference/main.py
```

**macOS or Linux**

```bash
export RAI_BASE_URL=http://localhost:8001
export RAI_ADMIN_EMAIL=admin@raigateway.local
export RAI_ADMIN_PASSWORD='ChangeMe123!'
python examples/support_ai_reference/main.py
```

When the API is running inside Docker, the tool URL must be reachable from the container:

```text
RAI_TOOL_URL=http://host.docker.internal:8765/invoke
```

When the API is running on the host, use `http://127.0.0.1:8765/invoke`. `support_ai_reference` sets the Docker form unless you override it.

3. Register the rest of the lab, then run one system:

```text
python examples/developer_lab/provision.py
python examples/sales_ai_reference/main.py
python examples/knowledge_assistant_reference/main.py
python examples/coding_agent_reference/main.py
python examples/government_assistant_reference/main.py
```

`provision.py` is idempotent. It writes runtime credentials to `examples/developer_lab/.rai-lab.json`. Do not commit that file. Workspace changes land in `examples/developer_lab/state/records.json`. An allowed case adds a row. A deny or an approval hold leaves the file unchanged.

More detail is in [examples/developer_lab/README.md](examples/developer_lab/README.md).

## What is in the tree

- **Registry** — AI systems, agents, versions, and dependency records
- **Identity** — runtime identities and credentials for agents
- **Policy and approval** — rules, obligations, and action-bound human approval
- **Runtime enforcement** — authorize or deny tool, MCP, and model actions before execution
- **Risk, evidence, and reporting** — budgets, findings, trajectories, and portfolio overview
- **Team** — one directory of people, departments, and governance roles
- **SDKs** — Python and TypeScript clients under `packages/`
- **Console** — Next.js app in `control-plane-ui/`

## Documentation

- [Deploy with Docker](docs/deployment/docker.md)
- [Development guide](DEVELOPMENT.md)
- [Documentation index](docs/DOCUMENTATION_INDEX.md)
- [Integration quickstart](docs/public/getting-started/quickstart.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
