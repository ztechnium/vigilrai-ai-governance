"""Database schema tests."""

from sqlalchemy import inspect


def test_core_tables_exist(db_session):
    inspector = inspect(db_session.bind)
    table_names = set(inspector.get_table_names())

    expected = {
        "prompts",
        "prompt_versions",
        "prompt_allowlist",
        "api_keys",
        "executions_audit",
    }

    missing = expected - table_names
    assert not missing, f"Missing tables: {sorted(missing)}"
