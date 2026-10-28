"""
Tests for the `flask seed` command.
"""

from sqlalchemy import func, select

from app.cli import ALICE_ID, sample_data
from app.db.models import User


def test_seed_inserts_sample_data(app, db_session):
    result = app.test_cli_runner().invoke(args=["seed"])

    assert result.exit_code == 0
    assert f"{len(sample_data())} records inserted" in result.output
    assert db_session.get(User, ALICE_ID) is not None


def test_seed_skips_existing_records(app, db_session):
    runner = app.test_cli_runner()
    runner.invoke(args=["seed"])

    result = runner.invoke(args=["seed"])

    assert result.exit_code == 0
    assert "0 records inserted" in result.output
    assert db_session.scalar(select(func.count()).select_from(User)) == 2


def test_seed_skips_soft_deleted_records(app, db_session):
    runner = app.test_cli_runner()
    runner.invoke(args=["seed"])
    db_session.get(User, ALICE_ID).soft_delete()
    db_session.commit()

    result = runner.invoke(args=["seed"])

    assert result.exit_code == 0
    assert "0 records inserted" in result.output
