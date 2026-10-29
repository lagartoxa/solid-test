"""
Tests for POST /payments/webhook (diagram 03).
"""

import uuid

import pytest
from sqlalchemy.orm.exc import StaleDataError

from app.db.constants import CartStatus, PaymentStatus
from app.db.models import Cart, Payment, Product
from app.db.repositories import CartRepository, PaymentRepository
from app.services.payment_service import PaymentService
from tests.factories import (
    assert_error,
    assert_validation_error,
    make_shop,
    post_payment,
    post_webhook,
    webhook_body,
)


@pytest.fixture
def started(client, db_session):
    """A shop whose payment was started (pending, stock reserved)."""
    shop = make_shop(db_session)
    response = post_payment(client, shop.cart.id, shop.method.id, shop.user.id)
    payment = db_session.get(Payment, uuid.UUID(response.json["id"]))

    return shop, payment


# ============================================================================
# 200 - RESULT APPLIED
# ============================================================================


def test_succeeded_checks_out_the_cart(client, db_session, started):
    shop, payment = started

    response = post_webhook(client, webhook_body(payment, "succeeded"))

    assert response.status_code == 200
    assert response.json["status"] == PaymentStatus.SUCCEEDED.value
    assert response.json["provider_transaction_id"] == "mock_tx_final"
    assert db_session.get(Cart, shop.cart.id).status == CartStatus.CHECKED_OUT.value
    # The reserved stock is now sold.
    assert db_session.get(Product, shop.product_a.id).stock_quantity == 3

    with CartRepository(db_session) as carts:
        assert [h.status for h in carts.get_history(shop.cart.id)] == ["active", "checked_out"]
    with PaymentRepository(db_session) as payments:
        assert [h.status for h in payments.get_history(payment.id)] == ["pending", "pending", "succeeded"]


def test_failed_gives_stock_back_and_keeps_cart_active(client, db_session, started):
    shop, payment = started

    response = post_webhook(client, webhook_body(payment, "failed", "insufficient funds"))

    assert response.status_code == 200
    assert response.json["status"] == PaymentStatus.FAILED.value
    assert response.json["failure_reason"] == "insufficient funds"
    assert db_session.get(Cart, shop.cart.id).status == CartStatus.ACTIVE.value
    assert db_session.get(Product, shop.product_a.id).stock_quantity == 5
    assert db_session.get(Product, shop.product_b.id).stock_quantity == 5


# ============================================================================
# 401 - SIGNATURE
# ============================================================================


def test_missing_signature(client, db_session, started):
    _, payment = started

    response = post_webhook(client, webhook_body(payment), signature=None)

    assert_error(db_session, response, 401, "invalid_signature")
    assert db_session.get(Payment, payment.id).status == PaymentStatus.PENDING.value


def test_wrong_signature(client, db_session, started):
    _, payment = started

    response = post_webhook(client, webhook_body(payment), signature="forged")

    assert_error(db_session, response, 401, "invalid_signature")


def test_signature_is_checked_before_the_body(client, db_session):
    response = post_webhook(client, {"not": "a valid body"}, signature=None)

    assert_error(db_session, response, 401, "invalid_signature")


# ============================================================================
# 422 - INVALID BODY
# ============================================================================


def test_invalid_body(client, db_session):
    assert_validation_error(db_session, post_webhook(client, {"payment_id": "not-a-uuid"}))


def test_unknown_status(client, db_session, started):
    _, payment = started

    assert_validation_error(db_session, post_webhook(client, webhook_body(payment, "refunded")))


def test_failed_without_reason(client, db_session, started):
    _, payment = started

    assert_validation_error(db_session, post_webhook(client, webhook_body(payment, "failed")))


# ============================================================================
# 404 / 409
# ============================================================================


def test_unknown_payment(client, db_session, started):
    _, payment = started
    body = webhook_body(payment) | {"payment_id": str(uuid.uuid4())}

    assert_error(db_session, post_webhook(client, body), 404, "payment_not_found")


@pytest.mark.parametrize(
    "first, second",
    [
        (("succeeded", None), ("succeeded", None)),
        (("succeeded", None), ("failed", "late failure")),
        (("failed", "insufficient funds"), ("succeeded", None)),
    ],
)
def test_payment_not_pending(client, db_session, started, first, second):
    _, payment = started
    post_webhook(client, webhook_body(payment, *first))

    response = post_webhook(client, webhook_body(payment, *second))

    assert_error(db_session, response, 409, "payment_not_pending")
    assert db_session.get(Payment, payment.id).status == first[0]


def test_concurrent_change(client, db_session, started, monkeypatch):
    _, payment = started

    def concurrent_change(*args, **kwargs):
        raise StaleDataError("payments row was changed by another request")

    monkeypatch.setattr(PaymentService, "apply_provider_result", concurrent_change)

    assert_error(db_session, post_webhook(client, webhook_body(payment)), 409, "concurrent_update")
