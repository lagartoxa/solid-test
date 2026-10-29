"""
Tests for POST /carts/{cart_id}/payments (diagram 02).
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.db.constants import CartStatus, LogAction, PaymentMethodType, PaymentStatus
from app.db.models import Cart, Payment, Product
from app.services.payment_provider import REFUSED_TOKEN, UNAVAILABLE_TOKEN
from app.services.payment_service import PaymentService
from tests.factories import (
    assert_error,
    assert_validation_error,
    logs_of,
    make_cart,
    make_payment,
    make_payment_method,
    make_product,
    make_shop,
    make_user,
    post_payment,
)


@pytest.fixture
def shop(db_session):
    return make_shop(db_session)


def pay(client, shop, **overrides):
    """Start the payment of the shop's cart, with optional overrides."""
    return post_payment(
        client,
        overrides.get("cart_id", shop.cart.id),
        overrides.get("payment_method_id", shop.method.id),
        overrides.get("user_id", shop.user.id),
    )


def stock_of(db_session, product):
    return db_session.get(Product, product.id).stock_quantity


def payments_of(db_session, cart):
    return list(db_session.scalars(select(Payment).where(Payment.cart_id == cart.id)))


# ============================================================================
# 202 - HAPPY PATH
# ============================================================================


@pytest.mark.parametrize("type", [PaymentMethodType.CREDIT, PaymentMethodType.DEBIT])
def test_payment_starts_with_credit_and_debit(client, db_session, type):
    shop = make_shop(db_session, type=type)

    response = pay(client, shop)

    assert response.status_code == 202
    body = response.json
    assert body["status"] == PaymentStatus.PENDING.value
    assert body["payment_type"] == type.value
    assert Decimal(body["amount"]) == Decimal("22.50")
    assert body["currency"] == "USD"
    assert body["provider_transaction_id"].startswith("mock_tx_")
    assert body["failure_reason"] is None

    # Stock is reserved; the cart stays active until the provider's result.
    assert stock_of(db_session, shop.product_a) == 3
    assert stock_of(db_session, shop.product_b) == 4
    assert db_session.get(Cart, shop.cart.id).status == CartStatus.ACTIVE.value

    actions = [log.action for log in logs_of(db_session, response)]
    assert actions.count(LogAction.EXTERNAL_CALL.value) == 2  # total calculation + provider
    assert LogAction.DB_CHANGE.value in actions
    assert actions[-1] == LogAction.API_REQUEST.value


def test_provider_token_is_masked_in_the_logs(client, db_session, shop):
    response = pay(client, shop)

    [provider_log] = [
        log for log in logs_of(db_session, response) if log.target == "payment_provider.start_charge"
    ]
    assert provider_log.request_payload["provider_token"] == "***"


def test_cart_can_be_paid_again_after_a_failed_payment(client, db_session, shop):
    make_payment(db_session, shop.cart, shop.method, status=PaymentStatus.FAILED)

    assert pay(client, shop).status_code == 202


# ============================================================================
# 402 / 502 - PROVIDER FAILS WHEN THE CHARGE STARTS
# ============================================================================


@pytest.mark.parametrize(
    "token, status, code, reason",
    [
        (REFUSED_TOKEN, 402, "payment_refused", "invalid card token"),
        (UNAVAILABLE_TOKEN, 502, "provider_unavailable", "payment provider is unavailable"),
    ],
)
def test_provider_failure_fails_the_payment_and_gives_stock_back(
    client, db_session, token, status, code, reason
):
    shop = make_shop(db_session, token=token)

    response = pay(client, shop)

    assert_error(db_session, response, status, code)

    [payment] = payments_of(db_session, shop.cart)
    assert payment.status == PaymentStatus.FAILED.value
    assert payment.failure_reason == reason
    assert stock_of(db_session, shop.product_a) == 5
    assert stock_of(db_session, shop.product_b) == 5
    assert db_session.get(Cart, shop.cart.id).status == CartStatus.ACTIVE.value

    [provider_log] = [
        log for log in logs_of(db_session, response) if log.target == "payment_provider.start_charge"
    ]
    assert reason in provider_log.error


def test_unexpected_provider_error_is_a_provider_failure(client, db_session, shop, monkeypatch):
    def broken_provider(self, charge):
        raise ConnectionError("connection reset")

    monkeypatch.setattr("app.services.payment_provider.MockPaymentProvider.start_charge", broken_provider)

    response = pay(client, shop)

    assert_error(db_session, response, 502, "provider_unavailable")
    [payment] = payments_of(db_session, shop.cart)
    assert payment.failure_reason == "connection reset"
    assert stock_of(db_session, shop.product_a) == 5


# ============================================================================
# 422 - INVALID INPUT
# ============================================================================


def test_missing_user_id_header(client, db_session, shop):
    assert_validation_error(db_session, pay(client, shop, user_id=None))


def test_invalid_user_id_header(client, db_session, shop):
    assert_validation_error(db_session, pay(client, shop, user_id="not-a-uuid"))


def test_invalid_cart_id(client, db_session, shop):
    assert_validation_error(db_session, pay(client, shop, cart_id="not-a-uuid"))


def test_invalid_payment_method_id(client, db_session, shop):
    assert_validation_error(db_session, pay(client, shop, payment_method_id="not-a-uuid"))


def test_missing_payment_method_id(client, db_session, shop):
    response = client.post(
        f"/carts/{shop.cart.id}/payments", json={}, headers={"User-Id": str(shop.user.id)}
    )

    assert_validation_error(db_session, response)


# ============================================================================
# 404 - USER OR CART NOT FOUND
# ============================================================================


def test_unknown_user(client, db_session, shop):
    assert_error(db_session, pay(client, shop, user_id=uuid.uuid4()), 404, "user_not_found")


def test_deleted_user(client, db_session):
    user = make_user(db_session, deleted=True)
    cart = make_cart(db_session, user, items=((make_product(db_session), 1),))
    method = make_payment_method(db_session, user)

    response = post_payment(client, cart.id, method.id, user.id)

    assert_error(db_session, response, 404, "user_not_found")


def test_unknown_cart(client, db_session, shop):
    assert_error(db_session, pay(client, shop, cart_id=uuid.uuid4()), 404, "cart_not_found")


def test_deleted_cart(client, db_session, shop):
    cart = make_cart(db_session, shop.user, items=((shop.product_a, 1),), deleted=True)

    assert_error(db_session, pay(client, shop, cart_id=cart.id), 404, "cart_not_found")


def test_cart_of_another_user(client, db_session, shop):
    other_user = make_user(db_session)

    assert_error(db_session, pay(client, shop, user_id=other_user.id), 404, "cart_not_found")


# ============================================================================
# 409 - CONFLICTS
# ============================================================================


@pytest.mark.parametrize("status", [CartStatus.CHECKED_OUT, CartStatus.ABANDONED])
def test_cart_not_active(client, db_session, shop, status):
    cart = make_cart(db_session, shop.user, items=((shop.product_a, 1),), status=status)

    assert_error(db_session, pay(client, shop, cart_id=cart.id), 409, "cart_not_active")


@pytest.mark.parametrize("status", [PaymentStatus.PENDING, PaymentStatus.SUCCEEDED])
def test_cart_with_active_payment(client, db_session, shop, status):
    make_payment(db_session, shop.cart, shop.method, status=status)

    assert_error(db_session, pay(client, shop), 409, "active_payment_exists")


def test_duplicate_request_does_not_charge_twice(client, db_session, shop):
    assert pay(client, shop).status_code == 202

    assert_error(db_session, pay(client, shop), 409, "active_payment_exists")
    assert len(payments_of(db_session, shop.cart)) == 1


def test_user_without_payment_methods(client, db_session):
    user = make_user(db_session)
    cart = make_cart(db_session, user, items=((make_product(db_session), 1),))

    response = post_payment(client, cart.id, uuid.uuid4(), user.id)

    assert_error(db_session, response, 409, "no_payment_method")


def test_unknown_payment_method(client, db_session, shop):
    response = pay(client, shop, payment_method_id=uuid.uuid4())

    assert_error(db_session, response, 409, "payment_method_not_found")


def test_deleted_payment_method(client, db_session, shop):
    deleted_method = make_payment_method(db_session, shop.user, deleted=True)

    response = pay(client, shop, payment_method_id=deleted_method.id)

    assert_error(db_session, response, 409, "payment_method_not_found")


def test_payment_method_of_another_user(client, db_session, shop):
    other_method = make_payment_method(db_session, make_user(db_session))

    response = pay(client, shop, payment_method_id=other_method.id)

    assert_error(db_session, response, 409, "payment_method_not_found")


def test_empty_cart(client, db_session, shop):
    empty_cart = make_cart(db_session, shop.user)

    assert_error(db_session, pay(client, shop, cart_id=empty_cart.id), 409, "cart_empty")


def test_deleted_product_in_cart(client, db_session, shop):
    deleted_product = make_product(db_session, deleted=True)
    cart = make_cart(db_session, shop.user, items=((shop.product_a, 1), (deleted_product, 1)))

    assert_error(db_session, pay(client, shop, cart_id=cart.id), 409, "product_unavailable")


def test_mixed_currencies(client, db_session, shop):
    euro_product = make_product(db_session, currency="EUR")
    cart = make_cart(db_session, shop.user, items=((shop.product_a, 1), (euro_product, 1)))

    assert_error(db_session, pay(client, shop, cart_id=cart.id), 409, "mixed_currencies")


def test_insufficient_stock(client, db_session, shop):
    cart = make_cart(db_session, shop.user, items=((shop.product_a, 6),))

    response = pay(client, shop, cart_id=cart.id)

    assert_error(db_session, response, 409, "insufficient_stock")
    assert stock_of(db_session, shop.product_a) == 5


def test_insufficient_stock_counts_repeated_products(client, db_session, shop):
    cart = make_cart(db_session, shop.user, items=((shop.product_a, 3), (shop.product_a, 3)))

    assert_error(db_session, pay(client, shop, cart_id=cart.id), 409, "insufficient_stock")


def test_rejected_request_changes_nothing(client, db_session, shop):
    cart = make_cart(db_session, shop.user, items=((shop.product_a, 1), (make_product(db_session, currency="EUR"), 1)))

    response = pay(client, shop, cart_id=cart.id)

    assert response.status_code == 409
    assert payments_of(db_session, cart) == []
    assert stock_of(db_session, shop.product_a) == 5
    assert [log.action for log in logs_of(db_session, response) if log.action == LogAction.DB_CHANGE.value] == []


# ============================================================================
# 409 - CONCURRENT REQUESTS
# ============================================================================


def test_concurrent_change_of_the_cart(client, db_session, shop, monkeypatch):
    def concurrent_change(*args, **kwargs):
        raise StaleDataError("carts row was changed by another request")

    monkeypatch.setattr(PaymentService, "start_payment", concurrent_change)

    assert_error(db_session, pay(client, shop), 409, "concurrent_update")


def test_concurrent_payment_of_the_same_cart(client, db_session, shop, monkeypatch):
    def second_active_payment(*args, **kwargs):
        raise IntegrityError(
            "INSERT INTO payments ...", {}, Exception('duplicate key value violates unique constraint "uq_payments_cart_id_active"')
        )

    monkeypatch.setattr(PaymentService, "start_payment", second_active_payment)

    assert_error(db_session, pay(client, shop), 409, "active_payment_exists")


def test_database_allows_only_one_active_payment_per_cart(db_session, shop):
    make_payment(db_session, shop.cart, shop.method, status=PaymentStatus.PENDING)

    with pytest.raises(IntegrityError, match="uq_payments_cart_id_active"):
        make_payment(db_session, shop.cart, shop.method, status=PaymentStatus.SUCCEEDED)
