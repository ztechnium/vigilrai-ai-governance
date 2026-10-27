# Test Taxonomy

## Layers

| Layer | Location | Database | External APIs |
|-------|----------|----------|---------------|
| Unit | `tests/services/`, `tests/unit/` | Mocked or fixture DB | Mocked |
| API | `tests/api/` | Isolated schema + Alembic | Mocked |
| DB | `tests/db/` | Real PostgreSQL | None |
| Integration | `tests/integration/` | Isolated schema + Alembic | Mocked LLM |
| Architecture | `tests/architecture/` | Isolated schema + Alembic | Mocked |
| E2E | `tests/e2e/` | Isolated schema + Alembic | Mocked LLM |
| Frontend unit | `control-plane-ui/tests/unit/` | None | Mocked |
| Browser E2E | `control-plane-ui/tests/e2e/` | None | Optional API |

## PostgreSQL Requirement

Core backend tests use **real PostgreSQL** via `TEST_DATABASE_URL`. Tests fail clearly if PostgreSQL is unavailable (no silent skip for core suites).

## Skip Policy

- Core database, migration, and governance-path tests must not be skipped in CI.
- Optional external provider integration tests require protected credentials and must be marked explicitly outside default PR gates.

## Mocking

- LLM providers: always mocked in default test suite (`mock_llm_provider` fixture).
- SIEM/OTEL: no-op unless explicitly testing observability wiring.

## Local Execution

```bash
export TEST_DATABASE_URL=postgresql://rai_user:rai_password@localhost:5434/rai_gateway
make test
```
