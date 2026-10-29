"""
Tests for GET /logs and GET /logs/{log_id}.
"""

import uuid

import pytest

from app.db.constants import LogAction
from tests.factories import (
    assert_error,
    assert_validation_error,
    get_payment,
    logs_of,
    make_shop,
    post_payment,
)


def failing_request(client, user_id="user-1"):
    """A request that fails (422 for an invalid User-Id, 404 otherwise) and leaves one api_request log."""
    return client.get(
        f"/carts/{uuid.uuid4()}/payments/{uuid.uuid4()}", headers={"User-Id": user_id}
    )


def api_log_of(db_session, response):
    [log] = [log for log in logs_of(db_session, response) if log.action == LogAction.API_REQUEST.value]
    return log


# ============================================================================
# GET /logs/{log_id}
# ============================================================================


def test_get_log_by_id(client, db_session):
    log = api_log_of(db_session, failing_request(client))

    response = client.get(f"/logs/{log.id}")

    assert response.status_code == 200
    assert response.json["id"] == str(log.id)
    assert response.json["action"] == LogAction.API_REQUEST.value
    assert response.json["status_code"] == 422  # "user-1" is not a UUID
    assert response.json["request_payload"]["headers"]["User-Id"] == "user-1"


def test_get_log_of_an_unexpected_error_by_its_log_id(client, db_session, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.payment_service.PaymentService.get_payment", broken)
    shop = make_shop(db_session)
    error = get_payment(client, shop.cart.id, uuid.uuid4(), shop.user.id)

    response = client.get(f"/logs/{error.json['log_id']}")

    assert response.status_code == 200
    assert "RuntimeError: boom" in response.json["error"]


def test_unknown_log(client, db_session):
    assert_error(db_session, client.get(f"/logs/{uuid.uuid4()}"), 404, "log_not_found")


def test_invalid_log_id(client, db_session):
    assert_validation_error(db_session, client.get("/logs/not-a-uuid"))


# ============================================================================
# GET /logs - FILTERS
# ============================================================================


def search(client, **query):
    response = client.get("/logs", query_string=query)
    assert response.status_code == 200, response.json
    return response.json


def test_filter_by_request_id_returns_every_log_of_the_request(client, db_session):
    shop = make_shop(db_session)
    started = post_payment(client, shop.cart.id, shop.method.id, shop.user.id)

    page = search(client, request_id=started.headers["X-Request-ID"])

    actions = {item["action"] for item in page["items"]}
    assert actions == {"api_request", "db_change", "external_call"}
    assert page["total"] == len(logs_of(db_session, started))


def test_filter_by_action_and_status_code(client, db_session):
    failing_request(client, user_id=str(uuid.uuid4()))

    page = search(client, action="api_request", status_code=404)

    assert page["total"] == 1
    assert page["items"][0]["status_code"] == 404


def test_filter_by_user_id_and_target(client, db_session):
    user_id = str(uuid.uuid4())
    failing_request(client, user_id=user_id)
    failing_request(client, user_id=str(uuid.uuid4()))

    page = search(client, user_id=user_id, action="api_request")

    assert page["total"] == 1
    assert page["items"][0]["target"].startswith("GET /carts/")
    assert search(client, target="payment_provider.start_charge")["total"] == 0


def test_filter_by_record_id_returns_the_changes_of_a_record(client, db_session):
    shop = make_shop(db_session)
    started = post_payment(client, shop.cart.id, shop.method.id, shop.user.id)

    page = search(client, record_id=started.json["id"])

    assert [item["target"] for item in page["items"]] == ["payments", "payments"]
    assert {item["operation"] for item in page["items"]} == {"insert", "update"}


def test_unknown_action(client, db_session):
    assert_validation_error(db_session, client.get("/logs", query_string={"action": "deleted"}))


# ============================================================================
# GET /logs - ORDER AND PAGINATION
# ============================================================================


def test_newest_first_with_pagination(client, db_session):
    for _ in range(3):
        failing_request(client, user_id="paging")

    first = search(client, user_id="paging", limit=2)
    second = search(client, user_id="paging", limit=2, offset=2)

    assert first["total"] == second["total"] == 3
    assert (first["limit"], first["offset"]) == (2, 0)
    assert len(first["items"]) == 2 and len(second["items"]) == 1

    created = [item["created_at"] for item in first["items"] + second["items"]]
    assert created == sorted(created, reverse=True)


@pytest.mark.parametrize("query", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_invalid_pagination(client, db_session, query):
    assert_validation_error(db_session, client.get("/logs", query_string=query))


# ============================================================================
# HOW THE LOG ENDPOINTS ARE LOGGED
# ============================================================================


def test_listing_is_logged_as_a_summary(client, db_session):
    failing_request(client)

    response = client.get("/logs", query_string={"action": "api_request"})

    log = api_log_of(db_session, response)
    assert log.response_payload == {"returned": 1, "total": 1}
    assert log.request_payload["query"] == {"action": ["api_request"]}


def test_get_by_id_is_logged_as_a_summary(client, db_session):
    log_id = api_log_of(db_session, failing_request(client)).id

    response = client.get(f"/logs/{log_id}")

    assert api_log_of(db_session, response).response_payload == {"log_id": str(log_id)}


def test_errors_of_the_log_endpoints_are_logged_in_full(client, db_session):
    response = client.get(f"/logs/{uuid.uuid4()}")

    assert api_log_of(db_session, response).response_payload["error"] == "log_not_found"
