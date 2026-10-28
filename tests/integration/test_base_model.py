"""
Tests for the columns every table inherits from BaseModel.
"""

from app.db.models import User


def test_insert_sets_id_and_timestamps(db_session):
    user = User(email="carol@example.com", name="Carol")
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)

    assert user.id is not None
    assert user.created_at is not None
    assert user.updated_at is not None
    assert user.deleted_at is None
    assert user.deleted is False


def test_update_refreshes_updated_at(db_session):
    user = User(email="carol@example.com", name="Carol")
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)
    created_at = user.created_at
    first_updated_at = user.updated_at

    user.name = "Carol Smith"
    db_session.flush()
    db_session.refresh(user)

    assert user.updated_at > first_updated_at
    assert user.created_at == created_at


def test_soft_delete_and_restore(db_session):
    user = User(email="carol@example.com", name="Carol")

    user.soft_delete()
    assert user.deleted is True
    assert user.deleted_at is not None

    user.restore()
    assert user.deleted is False
    assert user.deleted_at is None
