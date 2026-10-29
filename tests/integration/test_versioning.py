"""
Tests for versioned models (VersionedBaseModel) and their history.
"""

import pytest
from sqlalchemy import update
from sqlalchemy.orm.exc import StaleDataError

from app.db.constants import CartStatus, ChangeOperation
from app.db.models import Base, Cart, CartHistory, User
from app.db.repositories import CartRepository, UserRepository
from app.schemas import CartCreate, CartUpdate, UserCreate


@pytest.fixture
def user(db_session):
    with UserRepository(db_session) as repo:
        return repo.create(UserCreate(email="carol@example.com", name="Carol"))


@pytest.fixture
def cart(db_session, user):
    with CartRepository(db_session) as repo:
        return repo.create(CartCreate(user_id=user.id))


def history_of(db_session, cart_id):
    with CartRepository(db_session) as repo:
        return repo.get_history(cart_id)


def test_insert_writes_version_1(db_session, cart):
    history = history_of(db_session, cart.id)

    assert [(h.version, h.operation, h.status) for h in history] == [
        (1, ChangeOperation.INSERT.value, CartStatus.ACTIVE.value)
    ]
    assert history[0].user_id == cart.user_id
    assert history[0].changed_at is not None


def test_status_change_writes_new_version(db_session, cart):
    with CartRepository(db_session) as repo:
        updated = repo.update(cart.id, CartUpdate(status=CartStatus.CHECKED_OUT))

    history = history_of(db_session, cart.id)

    assert updated.version == 2
    assert [(h.version, h.operation, h.status) for h in history] == [
        (1, ChangeOperation.INSERT.value, CartStatus.ACTIVE.value),
        (2, ChangeOperation.UPDATE.value, CartStatus.CHECKED_OUT.value),
    ]


def test_update_without_real_change_writes_no_history(db_session, cart):
    with CartRepository(db_session) as repo:
        repo.update(cart.id, CartUpdate(status=CartStatus.ACTIVE))

    assert len(history_of(db_session, cart.id)) == 1


def test_soft_delete_and_restore_are_recorded_as_updates(db_session, cart):
    with CartRepository(db_session) as repo:
        repo.delete(cart.id)
    with CartRepository(db_session) as repo:
        repo.restore(cart.id)

    history = history_of(db_session, cart.id)

    assert [(h.version, h.operation) for h in history] == [
        (1, ChangeOperation.INSERT.value),
        (2, ChangeOperation.UPDATE.value),
        (3, ChangeOperation.UPDATE.value),
    ]
    assert history[1].deleted_at is not None
    assert history[2].deleted_at is None


def test_hard_delete_is_recorded(db_session, cart):
    db_session.delete(db_session.get(Cart, cart.id))
    db_session.flush()

    history = history_of(db_session, cart.id)

    assert history[-1].operation == ChangeOperation.DELETE.value
    assert history[-1].version == 2


def test_rollback_discards_history(db_session, user):
    with pytest.raises(RuntimeError):
        with CartRepository(db_session) as repo:
            cart = repo.create(CartCreate(user_id=user.id))
            raise RuntimeError("boom")

    assert history_of(db_session, cart.id) == []


def test_stale_update_raises_instead_of_overwriting(db_session, cart):
    loaded = db_session.get(Cart, cart.id)
    # Another process updates the cart in between (bulk update, so the
    # in-memory instance still has version 1).
    db_session.execute(
        update(Cart)
        .where(Cart.id == cart.id)
        .values(version=Cart.version + 1)
        .execution_options(synchronize_session=False)
    )

    loaded.status = CartStatus.ABANDONED.value

    with pytest.raises(StaleDataError):
        db_session.flush()


def test_non_versioned_model_has_no_history(user):
    assert not hasattr(User, "__history_class__")
    assert "users_history" not in Base.metadata.tables


def test_history_table_structure():
    columns = CartHistory.__table__.columns

    assert set(columns.keys()) == {
        "history_id", "id", "user_id", "status", "version", "deleted_at",
        "operation", "changed_at",
    }
    assert columns["history_id"].primary_key
    assert not CartHistory.__table__.foreign_keys
