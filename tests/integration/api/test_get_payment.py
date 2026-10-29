"""
Tests for GET /carts/{cart_id}/payments/{payment_id} (diagram 04).
"""

import uuid

import pytest

from app.db.constants import PaymentStatus
from tests.factories import (
    assert_error,
    assert_validation_error,
    get_payment,
    make_cart,
    make_payment,
    make_shop,
    make_user,
)


@pytest.fixture
def paid(db_session):
    shop = make_shop(db_session)
    payment = make_payment(db_session, shop.cart, shop.method, status=PaymentStatus.PENDING)

    return shop, payment


def test_returns_the_payment(client, db_session, paid):
    shop, payment = paid

    response = get_payment(client, shop.cart.id, payment.id, shop.user.id)

    assert response.status_code == 200
    assert response.json["id"] == str(payment.id)
    assert response.json["status"] == PaymentStatus.PENDING.value
    assert response.json["payment_type"] == shop.method.type


def test_invalid_ids(client, db_session, paid):
    shop, payment = paid

    assert_validation_error(db_session, get_payment(client, "not-a-uuid", payment.id, shop.user.id))
    assert_validation_error(db_session, get_payment(client, shop.cart.id, "not-a-uuid", shop.user.id))
    assert_validation_error(db_session, get_payment(client, shop.cart.id, payment.id, "not-a-uuid"))


def test_unknown_cart(client, db_session, paid):
    shop, payment = paid

    response = get_payment(client, uuid.uuid4(), payment.id, shop.user.id)

    assert_error(db_session, response, 404, "cart_not_found")


def test_cart_of_another_user(client, db_session, paid):
    shop, payment = paid

    response = get_payment(client, shop.cart.id, payment.id, make_user(db_session).id)

    assert_error(db_session, response, 404, "cart_not_found")


def test_unknown_payment(client, db_session, paid):
    shop, _ = paid

    response = get_payment(client, shop.cart.id, uuid.uuid4(), shop.user.id)

    assert_error(db_session, response, 404, "payment_not_found")


def test_payment_of_another_cart(client, db_session, paid):
    shop, payment = paid
    other_cart = make_cart(db_session, shop.user)

    response = get_payment(client, other_cart.id, payment.id, shop.user.id)

    assert_error(db_session, response, 404, "payment_not_found")
