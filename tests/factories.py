"""
Test data factories and request helpers shared by the API tests.

Factories commit, so the data survives the rollback of a request that fails
(each test still runs inside a transaction that is rolled back at the end).
"""

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from flask.testing import FlaskClient
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

from app.config import TestingConfig
from app.db.constants import CartStatus, LogAction, PaymentMethodType, PaymentStatus
from app.db.models import Cart, CartItem, Log, Payment, Product, User, UserPaymentMethod
from app.db.models.base import BaseModel
from app.db.repositories import LogRepository
from app.log.request_logging import REQUEST_ID_HEADER
from app.services.webhook_signature import SIGNATURE_HEADER, sign

SUCCESS_TOKEN = "tok_success"


def save(session: Session, record: BaseModel, deleted: bool = False) -> BaseModel:
    """
    Insert a record (soft-deleted if asked), commit and detach it.

    Detached records keep their loaded values, so a request that fails and
    rolls back the shared test session can't expire them.
    """
    if deleted:
        record.soft_delete()

    session.add(record)
    session.commit()
    session.refresh(record)
    session.expunge(record)

    return record


def make_user(session: Session, deleted: bool = False) -> User:
    return save(session, User(email=f"{uuid.uuid4().hex}@example.com", name="User"), deleted)


def make_product(
    session: Session,
    price: str = "10.00",
    currency: str = "USD",
    stock: int = 10,
    deleted: bool = False,
) -> Product:
    product = Product(name="Product", price=Decimal(price), currency=currency, stock_quantity=stock)
    return save(session, product, deleted)


def make_cart(
    session: Session,
    user: User,
    items: tuple[tuple[Product, int], ...] = (),
    status: CartStatus = CartStatus.ACTIVE,
    deleted: bool = False,
) -> Cart:
    cart = save(session, Cart(user_id=user.id, status=status.value), deleted)

    for product, quantity in items:
        save(
            session,
            CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity, unit_price=product.price),
        )

    return cart


def make_payment_method(
    session: Session,
    user: User,
    token: str = SUCCESS_TOKEN,
    type: PaymentMethodType = PaymentMethodType.CREDIT,
    deleted: bool = False,
) -> UserPaymentMethod:
    method = UserPaymentMethod(user_id=user.id, provider_token=token, type=type.value, last_four="4242")
    return save(session, method, deleted)


def make_payment(
    session: Session,
    cart: Cart,
    method: UserPaymentMethod,
    status: PaymentStatus = PaymentStatus.PENDING,
) -> Payment:
    payment = Payment(
        cart_id=cart.id,
        user_id=cart.user_id,
        payment_method_id=method.id,
        payment_type=method.type,
        amount=Decimal("10.00"),
        currency="USD",
        status=status.value,
        provider_transaction_id="mock_tx_test",
    )
    return save(session, payment)


@dataclass
class Shop:
    """A user with a payable cart: 2 x product_a + 1 x product_b, and a credit card."""

    user: User
    product_a: Product
    product_b: Product
    cart: Cart
    method: UserPaymentMethod


def make_shop(session: Session, token: str = SUCCESS_TOKEN, type: PaymentMethodType = PaymentMethodType.CREDIT) -> Shop:
    user = make_user(session)
    product_a = make_product(session, price="10.00", stock=5)
    product_b = make_product(session, price="2.50", stock=5)
    cart = make_cart(session, user, items=((product_a, 2), (product_b, 1)))
    method = make_payment_method(session, user, token=token, type=type)

    return Shop(user, product_a, product_b, cart, method)


# ============================================================================
# REQUESTS
# ============================================================================


def post_payment(
    client: FlaskClient,
    cart_id: object,
    payment_method_id: object,
    user_id: Optional[object],
) -> TestResponse:
    headers = {} if user_id is None else {"User-Id": str(user_id)}
    return client.post(
        f"/carts/{cart_id}/payments",
        json={"payment_method_id": str(payment_method_id)},
        headers=headers,
    )


def get_payment(client: FlaskClient, cart_id: object, payment_id: object, user_id: object) -> TestResponse:
    return client.get(f"/carts/{cart_id}/payments/{payment_id}", headers={"User-Id": str(user_id)})


def post_webhook(client: FlaskClient, body: dict, signature: Optional[str] = "sign") -> TestResponse:
    """
    Call the webhook. signature="sign" signs the body with the test secret;
    None sends no signature; any other value is sent as is.
    """
    raw = json.dumps(body).encode()
    headers = {}

    if signature == "sign":
        headers[SIGNATURE_HEADER] = sign(raw, TestingConfig.WEBHOOK_SECRET)
    elif signature is not None:
        headers[SIGNATURE_HEADER] = signature

    return client.post("/payments/webhook", data=raw, content_type="application/json", headers=headers)


def webhook_body(payment: Payment, status: str = "succeeded", failure_reason: Optional[str] = None) -> dict:
    return {
        "payment_id": str(payment.id),
        "provider_transaction_id": "mock_tx_final",
        "status": status,
        "failure_reason": failure_reason,
    }


# ============================================================================
# ASSERTIONS
# ============================================================================


def logs_of(session: Session, response: TestResponse) -> list[Log]:
    with LogRepository(session) as repo:
        return repo.get_by_request_id(uuid.UUID(response.headers[REQUEST_ID_HEADER]))


def assert_error(session: Session, response: TestResponse, status: int, code: str) -> None:
    """The response is the business error, and the request's API log has it."""
    assert response.status_code == status, response.json
    assert response.json["error"] == code

    [api_log] = [log for log in logs_of(session, response) if log.action == LogAction.API_REQUEST.value]
    assert api_log.status_code == status
    assert api_log.response_payload["error"] == code


def assert_validation_error(session: Session, response: TestResponse) -> None:
    """422 from the schema validation, logged too."""
    assert response.status_code == 422, response.json

    [api_log] = [log for log in logs_of(session, response) if log.action == LogAction.API_REQUEST.value]
    assert api_log.status_code == 422
