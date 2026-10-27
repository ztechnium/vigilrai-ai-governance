# VigilRAI Community Edition. Install and test with uv. Docker is not required for these targets except dev, up, and build.
.PHONY: setup dev up lint format format-check typecheck test test-unit test-integration test-e2e migrate migration-check build security docs ci seed-mcp-catalog attach-seeded-mcp

PYTHON ?= uv run
PNPM_VERSION ?= 9.15.0
PNPM ?= pnpm --dir control-plane-ui

prepare-pnpm:
	corepack enable
	corepack prepare pnpm@$(PNPM_VERSION) --activate

setup: prepare-pnpm
	uv sync --extra dev
	$(PNPM) install --frozen-lockfile

# Hot-reload stack (API --reload + Next.js `next dev`).
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Production-style stack: UI image builds then runs `next start`.
up:
	docker compose up --build

lint:
	$(PYTHON) ruff check .
	$(PNPM) run lint

format:
	$(PYTHON) ruff format .
	$(PNPM) run format

format-check:
	$(PYTHON) ruff format --check .
	$(PNPM) run format:check

typecheck:
	$(PYTHON) mypy src/rai_gateway/core/health.py src/rai_gateway/core/version_info.py src/rai_gateway/core/database.py
	$(PNPM) run typecheck

test: test-unit test-integration

test-unit:
	$(PYTHON) pytest tests/services tests/api tests/architecture tests/db tests/registry tests/approval tests/identity tests/policy tests/runtime_enforcement tests/client_hooks tests/evidence -q
	$(PNPM) run test:unit

test-integration:
	TEST_DATABASE_URL=$${TEST_DATABASE_URL:-postgresql://rai_user:rai_password@localhost:5434/rai_gateway} \
		$(PYTHON) pytest tests/integration -q

test-e2e:
	TEST_DATABASE_URL=$${TEST_DATABASE_URL:-postgresql://rai_user:rai_password@localhost:5434/rai_gateway} \
		$(PYTHON) pytest tests/e2e -q
	$(PNPM) run test:e2e

migrate:
	$(PYTHON) alembic upgrade head

migration-check:
	TEST_DATABASE_URL=$${TEST_DATABASE_URL:-postgresql://rai_user:rai_password@localhost:5434/rai_gateway} \
		$(PYTHON) pytest tests/db/test_migrations.py -q

build:
	docker compose build
	$(PNPM) run build

security:
	$(PYTHON) pip-audit
	$(PNPM) audit --audit-level moderate || true

docs:
	@echo "See DEVELOPMENT.md and docs/"

# Prefer seeding inside the running compose stack (uses container DATABASE_URL).
# Fallback: host run against localhost:5434 after postgres port is published.
seed-mcp-catalog:
	@if docker compose ps --status running --services 2>/dev/null | grep -qx rai-gateway; then \
		docker compose exec -T rai-gateway python /app/scripts/seed_mcp_catalog.py; \
	else \
		DATABASE_URL=$${DATABASE_URL:-postgresql://rai_user:rai_password@localhost:5434/rai_gateway} \
			$(PYTHON) scripts/seed_mcp_catalog.py; \
	fi

# Example:
#   make attach-seeded-mcp VERSION_ID=ada35d01-22d0-4a11-8e13-2323d9e328f5
attach-seeded-mcp:
	@test -n "$(VERSION_ID)" || (echo "VERSION_ID is required" && exit 1)
	@if docker compose ps --status running --services 2>/dev/null | grep -qx rai-gateway; then \
		docker compose exec -T rai-gateway python /app/scripts/attach_seeded_mcp_to_version.py \
			--version-id $(VERSION_ID) \
			--mcp-key atlassian \
			--mcp-key cursor_local \
			--expand-delegations; \
	else \
		DATABASE_URL=$${DATABASE_URL:-postgresql://rai_user:rai_password@localhost:5434/rai_gateway} \
			$(PYTHON) scripts/attach_seeded_mcp_to_version.py \
			--version-id $(VERSION_ID) \
			--mcp-key atlassian \
			--mcp-key cursor_local \
			--expand-delegations; \
	fi

ci: setup lint format-check typecheck migration-check test build security
