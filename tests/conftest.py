"""
Test configuration and fixtures.

The tests run against a real PostgreSQL database (shop_test), migrated with
Alembic once per test session. Each test runs inside a transaction that is
rolled back at the end, so tests never see each other's data.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import create_app
from app.config import TestingConfig

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def test_engine():
    """
    Migrate the test database to the latest revision (session-scoped).

    Downgrades everything at the end so the next run starts from scratch.
    """
    alembic_config = AlembicConfig(str(ALEMBIC_INI))
    alembic_config.set_main_option("sqlalchemy.url", TestingConfig.DATABASE_URL)
    alembic_config.attributes["configure_logger"] = False

    command.upgrade(alembic_config, "head")

    engine = create_engine(TestingConfig.DATABASE_URL)

    yield engine

    engine.dispose()
    command.downgrade(alembic_config, "base")


@pytest.fixture
def db_session(test_engine):
    """
    Database session wrapped in a transaction that is rolled back after the test.

    Commits made by the code under test become savepoints, so repositories can
    commit normally without leaking data between tests.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ============================================================================
# APP FIXTURES
# ============================================================================

@pytest.fixture
def app(db_session):
    """Flask app whose requests use the test session."""
    app = create_app(TestingConfig)
    app.extensions["session_factory"] = lambda: db_session

    return app


@pytest.fixture
def client(app):
    """Flask test client for the endpoint tests."""
    return app.test_client()
