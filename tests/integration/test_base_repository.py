"""
Tests for the generic CRUD operations of BaseRepository.
"""

import uuid

import pytest

from app.db.repositories import ProductRepository, UserRepository
from app.schemas import ProductCreate, UserCreate, UserUpdate


@pytest.fixture
def user(db_session):
    with UserRepository(db_session) as repo:
        return repo.create(UserCreate(email="carol@example.com", name="Carol"))


def ids(records):
    return [record.id for record in records]


def test_create_returns_persisted_instance(db_session, user):
    with UserRepository(db_session) as repo:
        found = repo.get_by_id(user.id)

    assert found is not None
    assert found.email == "carol@example.com"
    assert found.created_at is not None


def test_get_by_id_returns_none_when_missing(db_session):
    with UserRepository(db_session) as repo:
        assert repo.get_by_id(uuid.uuid4()) is None


def test_update_changes_only_given_fields(db_session, user):
    with UserRepository(db_session) as repo:
        updated = repo.update(user.id, UserUpdate(name="Carol Smith"))

    assert updated.name == "Carol Smith"
    assert updated.email == "carol@example.com"


def test_update_returns_none_when_missing(db_session):
    with UserRepository(db_session) as repo:
        assert repo.update(uuid.uuid4(), UserUpdate(name="X")) is None


def test_delete_is_soft(db_session, user):
    with UserRepository(db_session) as repo:
        assert repo.delete(user.id) is True

    with UserRepository(db_session) as repo:
        assert repo.get_by_id(user.id) is None
        assert user.id not in ids(repo.get_all())

        deleted = repo.get_by_id(user.id, include_deleted=True)
        assert deleted is not None
        assert deleted.deleted_at is not None
        assert user.id in ids(repo.get_all(include_deleted=True))


def test_delete_returns_false_when_missing(db_session):
    with UserRepository(db_session) as repo:
        assert repo.delete(uuid.uuid4()) is False


def test_restore_brings_record_back(db_session, user):
    with UserRepository(db_session) as repo:
        repo.delete(user.id)

    with UserRepository(db_session) as repo:
        restored = repo.restore(user.id)

    assert restored.deleted_at is None
    with UserRepository(db_session) as repo:
        assert repo.get_by_id(user.id) is not None


def test_restore_returns_none_when_missing(db_session):
    with UserRepository(db_session) as repo:
        assert repo.restore(uuid.uuid4()) is None


def test_email_can_be_reused_after_soft_delete(db_session, user):
    with UserRepository(db_session) as repo:
        repo.delete(user.id)
        new_user = repo.create(UserCreate(email="carol@example.com", name="Carol 2"))

    with UserRepository(db_session) as repo:
        assert repo.get_by_email("carol@example.com").id == new_user.id


def test_context_manager_rolls_back_on_error(db_session):
    with pytest.raises(RuntimeError):
        with UserRepository(db_session) as repo:
            repo.create(UserCreate(email="dave@example.com", name="Dave"))
            raise RuntimeError("boom")

    with UserRepository(db_session) as repo:
        assert repo.get_by_email("dave@example.com") is None


def test_context_manager_closes_session(db_session, user):
    with UserRepository(db_session) as repo:
        found = repo.get_by_id(user.id)

    assert found not in db_session


def test_nested_repositories_share_the_transaction(db_session):
    with UserRepository(db_session) as users:
        with ProductRepository(db_session) as products:
            product = products.create(ProductCreate(name="Lamp", price="20.00"))

        # The inner with did not close the session.
        assert product in db_session
        user = users.create(UserCreate(email="erin@example.com", name="Erin"))

    with UserRepository(db_session) as users:
        with ProductRepository(db_session) as products:
            assert users.get_by_id(user.id) is not None
            assert products.get_by_id(product.id) is not None


def test_error_in_nested_repository_rolls_back_everything(db_session):
    with UserRepository(db_session) as users:
        users.create(UserCreate(email="frank@example.com", name="Frank"))

        with pytest.raises(RuntimeError):
            with ProductRepository(db_session) as products:
                products.create(ProductCreate(name="Lamp", price="20.00"))
                raise RuntimeError("boom")

    with UserRepository(db_session) as users:
        assert users.get_by_email("frank@example.com") is None
