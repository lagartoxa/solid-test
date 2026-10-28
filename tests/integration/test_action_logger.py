"""
Tests for the action log: API requests, database changes and external calls.
"""

import uuid

import pytest
from flask import jsonify, request
from sqlalchemy import select

from app.cli import ALICE_ID
from app.db.constants import MASK, ChangeOperation, LogAction
from app.db.models import Log
from app.db.repositories import LogRepository, UserRepository
from app.db.session import get_session
from app.log.action_logger import ActionLogger, action_logger, mask_sensitive, to_masked_json
from app.log.request_logging import REQUEST_ID_HEADER, UNEXPECTED_ERROR_MESSAGE
from app.schemas import UserCreate, UserUpdate


@pytest.fixture
def logged_app(app):
    """App with test-only routes."""

    def echo():
        return jsonify({"received": request.get_json(), "provider_token": "tok_secret"}), 201

    def create_user():
        with UserRepository(get_session()) as repo:
            user = repo.create(UserCreate(**request.get_json()))
        return {"id": str(user.id)}, 201

    def create_user_and_fail():
        with UserRepository(get_session()) as repo:
            repo.create(UserCreate(**request.get_json()))
            raise RuntimeError("boom")

    app.add_url_rule("/test/echo", view_func=echo, methods=["POST"])
    app.add_url_rule("/test/users", view_func=create_user, methods=["POST"])
    app.add_url_rule("/test/users-fail", view_func=create_user_and_fail, methods=["POST"])

    return app


def logs_of(db_session, response):
    with LogRepository(db_session) as repo:
        return repo.get_by_request_id(uuid.UUID(response.headers[REQUEST_ID_HEADER]))


def all_logs(db_session, action):
    return list(db_session.scalars(select(Log).where(Log.action == action.value)))


# ============================================================================
# SINGLETON AND MASKING
# ============================================================================

def test_action_logger_is_a_singleton():
    assert ActionLogger() is ActionLogger()
    assert ActionLogger() is action_logger


def test_sensitive_keys_are_masked_at_any_depth_ignoring_case():
    payload = {
        "Provider_Token": "tok_1",
        "name": "Alice",
        "methods": [{"token": "tok_2", "last_four": "4242"}],
        "headers": {"Authorization": "Bearer x"},
    }

    assert mask_sensitive(payload) == {
        "Provider_Token": MASK,
        "name": "Alice",
        "methods": [{"token": MASK, "last_four": "4242"}],
        "headers": {"Authorization": MASK},
    }


def test_payload_values_are_converted_to_json():
    record_id = uuid.uuid4()

    assert to_masked_json({"id": record_id}) == {"id": str(record_id)}
    assert to_masked_json(None) is None


# ============================================================================
# API REQUESTS
# ============================================================================

def test_api_request_is_logged_with_payloads(logged_app, db_session):
    response = logged_app.test_client().post(
        "/test/echo?source=test",
        json={"amount": "10.00", "token": "tok_secret"},
        headers={"User-Id": "user-123"},
    )

    [log] = logs_of(db_session, response)

    assert log.action == LogAction.API_REQUEST.value
    assert log.target == "POST /test/echo"
    assert log.status_code == 201
    assert log.user_id == "user-123"
    assert log.request_payload["query"] == {"source": ["test"]}
    assert log.request_payload["body"] == {"amount": "10.00", "token": MASK}
    assert log.request_payload["headers"]["User-Id"] == "user-123"
    assert log.response_payload["provider_token"] == MASK
    assert log.response_payload["received"]["token"] == MASK
    assert log.error is None
    assert log.duration_ms >= 0


def test_unexpected_error_returns_500_and_is_logged(logged_app, db_session):
    response = logged_app.test_client().post(
        "/test/users-fail", json={"email": "dave@example.com", "name": "Dave"}
    )

    request_id = response.headers[REQUEST_ID_HEADER]
    log_id = response.json["log_id"]

    assert response.status_code == 500
    assert response.json == {
        "error": UNEXPECTED_ERROR_MESSAGE.format(request_id=request_id, log_id=log_id),
        "request_id": request_id,
        "log_id": log_id,
    }
    assert response.json["error"] == (
        f"An unexpected error happened. Log id: {request_id}/{log_id}"
    )

    logs = logs_of(db_session, response)

    # The user insert was rolled back, so only the API request is logged.
    assert [log.action for log in logs] == [LogAction.API_REQUEST.value]
    assert str(logs[0].id) == log_id
    assert logs[0].status_code == 500
    assert "RuntimeError: boom" in logs[0].error


def test_http_errors_keep_default_handling_and_are_logged(logged_app, db_session):
    response = logged_app.test_client().get("/test/missing")

    assert response.status_code == 404
    assert logs_of(db_session, response)[0].status_code == 404


def test_docs_are_not_logged(logged_app, db_session):
    response = logged_app.test_client().get("/docs/")

    assert REQUEST_ID_HEADER in response.headers
    assert all_logs(db_session, LogAction.API_REQUEST) == []


def test_db_changes_of_a_request_share_its_request_id(logged_app, db_session):
    response = logged_app.test_client().post(
        "/test/users", json={"email": "erin@example.com", "name": "Erin"}
    )

    logs = logs_of(db_session, response)

    assert [log.action for log in logs] == [
        LogAction.DB_CHANGE.value,
        LogAction.API_REQUEST.value,
    ]
    assert logs[0].target == "users"
    assert str(logs[0].record_id) == response.json["id"]


# ============================================================================
# DATABASE CHANGES
# ============================================================================

def change_logs(db_session, record_id):
    query = select(Log).where(Log.record_id == record_id).order_by(Log.created_at)
    return list(db_session.scalars(query))


def test_repository_changes_are_logged(db_session):
    with UserRepository(db_session) as repo:
        user = repo.create(UserCreate(email="carol@example.com", name="Carol"))
    with UserRepository(db_session) as repo:
        repo.update(user.id, UserUpdate(name="Carol Smith"))
    with UserRepository(db_session) as repo:
        repo.delete(user.id)
    with UserRepository(db_session) as repo:
        repo.restore(user.id)

    logs = change_logs(db_session, user.id)

    assert [(log.action, log.target, log.operation) for log in logs] == [
        (LogAction.DB_CHANGE.value, "users", ChangeOperation.INSERT.value),
        (LogAction.DB_CHANGE.value, "users", ChangeOperation.UPDATE.value),
        (LogAction.DB_CHANGE.value, "users", ChangeOperation.UPDATE.value),
        (LogAction.DB_CHANGE.value, "users", ChangeOperation.UPDATE.value),
    ]
    insert, update, delete, restore = (log.request_payload for log in logs)
    assert insert["before"] is None
    assert insert["after"]["email"] == "carol@example.com"
    assert update == {"before": {"name": "Carol"}, "after": {"name": "Carol Smith"}}
    assert delete["before"] == {"deleted_at": None}
    assert delete["after"]["deleted_at"] is not None
    assert restore["after"] == {"deleted_at": None}
    assert logs[0].request_id is None


def test_update_without_real_change_is_not_logged(db_session):
    with UserRepository(db_session) as repo:
        user = repo.create(UserCreate(email="carol@example.com", name="Carol"))
    with UserRepository(db_session) as repo:
        repo.update(user.id, UserUpdate(name="Carol"))

    assert len(change_logs(db_session, user.id)) == 1


def test_rolled_back_change_is_not_logged(db_session):
    with pytest.raises(RuntimeError):
        with UserRepository(db_session) as repo:
            user = repo.create(UserCreate(email="carol@example.com", name="Carol"))
            raise RuntimeError("boom")

    assert change_logs(db_session, user.id) == []


def test_seed_logs_its_inserts(app, db_session):
    app.test_cli_runner().invoke(args=["seed"])

    [log] = change_logs(db_session, ALICE_ID)

    assert log.target == "users"
    assert log.operation == ChangeOperation.INSERT.value
    assert log.request_payload["after"]["email"] == "alice@example.com"


# ============================================================================
# EXTERNAL CALLS
# ============================================================================

def test_external_call_is_logged(app, db_session):
    with app.app_context():
        with action_logger.external_call(
            "payment_provider", "charge", {"provider_token": "tok_1", "amount": "70.00"}
        ) as call:
            call.received = {"transaction_id": "tx_1", "status": "accepted"}

    [log] = all_logs(db_session, LogAction.EXTERNAL_CALL)

    assert log.target == "payment_provider.charge"
    assert log.request_payload == {"provider_token": MASK, "amount": "70.00"}
    assert log.response_payload == {"transaction_id": "tx_1", "status": "accepted"}
    assert log.error is None
    assert log.duration_ms >= 0


def test_failed_external_call_is_logged_and_raised(app, db_session):
    with app.app_context():
        with pytest.raises(TimeoutError):
            with action_logger.external_call("payment_provider", "charge", {"amount": "1.00"}):
                raise TimeoutError("provider timeout")

    [log] = all_logs(db_session, LogAction.EXTERNAL_CALL)

    assert log.response_payload is None
    assert "TimeoutError: provider timeout" in log.error
