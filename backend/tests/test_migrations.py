"""Tests for Alembic Database Migrations Clean Upgrade and Downgrade."""

import os
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from app.core.database import engine


def test_alembic_upgrade_and_downgrade():
    """Verifies that Alembic migrations run cleanly against a fresh SQLite/PostgreSQL database."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_ini_path = os.path.join(base_dir, "alembic.ini")

    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", "sqlite:///./test_migration.db")

    # Clean up any leftover test database file
    db_file = os.path.join(base_dir, "test_migration.db")
    if os.path.exists(db_file):
        os.remove(db_file)

    test_mig_engine = None
    try:
        # Run upgrade to head
        command.upgrade(alembic_cfg, "head")

        from sqlalchemy import create_engine
        test_mig_engine = create_engine("sqlite:///./test_migration.db")
        inspector = inspect(test_mig_engine)
        tables = inspector.get_table_names()

        assert "users" in tables
        assert "organizations" in tables
        assert "org_memberships" in tables
        assert "merchant_economics" in tables
        assert "revoked_tokens" in tables
        assert "audit_logs" in tables

        # Run downgrade to base
        command.downgrade(alembic_cfg, "base")
        inspector = inspect(test_mig_engine)
        tables_after = inspector.get_table_names()

        assert "audit_logs" not in tables_after
        assert "users" not in tables_after
        assert "organizations" not in tables_after

    finally:
        if test_mig_engine is not None:
            test_mig_engine.dispose()
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except OSError:
                pass
