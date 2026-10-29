"""
Flask CLI commands.
"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import click
from flask import Flask, current_app
from flask.cli import AppGroup, with_appcontext

from app.db.constants import CartStatus, ChangeOperation, PaymentMethodType
from app.db.models import BaseModel, Cart, CartItem, Product, User, UserPaymentMethod
from app.db.repositories import PaymentRepository
from app.db.session import get_session
from app.log.action_logger import action_logger
from app.services.payment_provider import (
    DECLINED_TOKEN,
    REFUSED_TOKEN,
    UNAVAILABLE_TOKEN,
    MockPaymentProvider,
)
from app.services.webhook_signature import SIGNATURE_HEADER, sign

ALICE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
BOB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
KETTLE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BLANKET_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
MUG_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
ALICE_CART_ID = uuid.UUID("c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1")
ALICE_CART_KETTLE_ID = uuid.UUID("d1d1d1d1-d1d1-d1d1-d1d1-d1d1d1d1d1d1")
ALICE_CART_MUG_ID = uuid.UUID("d2d2d2d2-d2d2-d2d2-d2d2-d2d2d2d2d2d2")
ALICE_CARD_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
# Extra sample data to try every outcome of the mock payment provider.
ALICE_DEBIT_CARD_ID = uuid.UUID("11111111-2222-3333-4444-666666666666")
ALICE_REFUSED_CARD_ID = uuid.UUID("11111111-2222-3333-4444-777777777777")
ALICE_UNAVAILABLE_CARD_ID = uuid.UUID("11111111-2222-3333-4444-888888888888")
ALICE_DECLINED_CREDIT_CARD_ID = uuid.UUID("11111111-2222-3333-4444-999999999999")
ALICE_DECLINED_DEBIT_CARD_ID = uuid.UUID("11111111-2222-3333-4444-aaaaaaaaaaaa")
BOB_CART_ID = uuid.UUID("c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2")
BOB_CART_BLANKET_ID = uuid.UUID("d3d3d3d3-d3d3-d3d3-d3d3-d3d3d3d3d3d3")
CAROL_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
CAROL_CART_ID = uuid.UUID("c3c3c3c3-c3c3-c3c3-c3c3-c3c3c3c3c3c3")
CAROL_CART_MUG_ID = uuid.UUID("d4d4d4d4-d4d4-d4d4-d4d4-d4d4d4d4d4d4")
CAROL_REFUSED_CARD_ID = uuid.UUID("33333333-2222-3333-4444-777777777777")
CAROL_UNAVAILABLE_CARD_ID = uuid.UUID("33333333-2222-3333-4444-888888888888")
CAROL_DECLINED_CREDIT_CARD_ID = uuid.UUID("33333333-2222-3333-4444-999999999999")
CAROL_DECLINED_DEBIT_CARD_ID = uuid.UUID("33333333-2222-3333-4444-aaaaaaaaaaaa")
# Dave: one cart per edge case of POST /carts/{cart_id}/payments, and a working card.
DAVE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
DAVE_CARD_ID = uuid.UUID("44444444-2222-3333-4444-555555555555")
DAVE_EMPTY_CART_ID = uuid.UUID("e0000000-0000-0000-0000-000000000001")
DAVE_CHECKED_OUT_CART_ID = uuid.UUID("e0000000-0000-0000-0000-000000000002")
DAVE_ABANDONED_CART_ID = uuid.UUID("e0000000-0000-0000-0000-000000000003")
DAVE_DELETED_CART_ID = uuid.UUID("e0000000-0000-0000-0000-000000000004")
DAVE_DELETED_PRODUCT_CART_ID = uuid.UUID("e0000000-0000-0000-0000-000000000005")
DAVE_MIXED_CURRENCY_CART_ID = uuid.UUID("e0000000-0000-0000-0000-000000000006")
DAVE_NO_STOCK_CART_ID = uuid.UUID("e0000000-0000-0000-0000-000000000007")
LAMP_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")  # soft-deleted product
TEA_SET_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")  # priced in EUR
SEED_DELETED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def register_cli(app: Flask) -> None:
    """Register the CLI commands on the app."""
    app.cli.add_command(seed)
    app.cli.add_command(mock_provider_cli)


def sample_data() -> list[BaseModel]:
    """
    Sample data from quick-start.sql, in insertion order (parents first).

    Every record has a fixed id, so the seed can tell if it was already inserted.
    Besides the quick-start data, Alice has one card per mock provider outcome,
    Bob (who has no payment method) has an active cart. Carol has an active cart
    and one card per failure of the provider, to test failures without using up
    Alice's cart (a failed payment leaves the cart active).
    Dave has a working card and one cart per edge case of starting a payment
    (so, unlike real data, he has more than one active cart).
    """
    return [
        User(id=ALICE_ID, email="alice@example.com", name="Alice"),
        User(id=BOB_ID, email="bob@example.com", name="Bob"),
        Product(id=KETTLE_ID, name="Blue Kettle", price=Decimal("45.00"), stock_quantity=10),
        Product(id=BLANKET_ID, name="Wool Blanket", price=Decimal("89.99"), stock_quantity=5),
        Product(id=MUG_ID, name="Ceramic Mug", price=Decimal("12.50"), stock_quantity=100),
        Cart(id=ALICE_CART_ID, user_id=ALICE_ID),
        CartItem(
            id=ALICE_CART_KETTLE_ID,
            cart_id=ALICE_CART_ID,
            product_id=KETTLE_ID,
            quantity=1,
            unit_price=Decimal("45.00"),
        ),
        CartItem(
            id=ALICE_CART_MUG_ID,
            cart_id=ALICE_CART_ID,
            product_id=MUG_ID,
            quantity=2,
            unit_price=Decimal("12.50"),
        ),
        UserPaymentMethod(
            id=ALICE_CARD_ID,
            user_id=ALICE_ID,
            provider_token="tok_test_alice_visa",
            type=PaymentMethodType.CREDIT.value,
            last_four="4242",
            is_default=True,
        ),
        sample_card(ALICE_DEBIT_CARD_ID, ALICE_ID, "tok_test_alice_debit", PaymentMethodType.DEBIT, "1881"),
        sample_card(ALICE_REFUSED_CARD_ID, ALICE_ID, REFUSED_TOKEN, PaymentMethodType.CREDIT, "0001"),
        sample_card(ALICE_UNAVAILABLE_CARD_ID, ALICE_ID, UNAVAILABLE_TOKEN, PaymentMethodType.CREDIT, "0002"),
        sample_card(ALICE_DECLINED_CREDIT_CARD_ID, ALICE_ID, DECLINED_TOKEN, PaymentMethodType.CREDIT, "0003"),
        sample_card(ALICE_DECLINED_DEBIT_CARD_ID, ALICE_ID, DECLINED_TOKEN, PaymentMethodType.DEBIT, "0004"),
        Cart(id=BOB_CART_ID, user_id=BOB_ID),
        CartItem(
            id=BOB_CART_BLANKET_ID,
            cart_id=BOB_CART_ID,
            product_id=BLANKET_ID,
            quantity=1,
            unit_price=Decimal("89.99"),
        ),
        User(id=CAROL_ID, email="carol@example.com", name="Carol"),
        Cart(id=CAROL_CART_ID, user_id=CAROL_ID),
        CartItem(
            id=CAROL_CART_MUG_ID,
            cart_id=CAROL_CART_ID,
            product_id=MUG_ID,
            quantity=1,
            unit_price=Decimal("12.50"),
        ),
        sample_card(CAROL_REFUSED_CARD_ID, CAROL_ID, REFUSED_TOKEN, PaymentMethodType.CREDIT, "0001"),
        sample_card(CAROL_UNAVAILABLE_CARD_ID, CAROL_ID, UNAVAILABLE_TOKEN, PaymentMethodType.CREDIT, "0002"),
        sample_card(CAROL_DECLINED_CREDIT_CARD_ID, CAROL_ID, DECLINED_TOKEN, PaymentMethodType.CREDIT, "0003"),
        sample_card(CAROL_DECLINED_DEBIT_CARD_ID, CAROL_ID, DECLINED_TOKEN, PaymentMethodType.DEBIT, "0004"),
        Product(
            id=LAMP_ID,
            name="Discontinued Lamp",
            price=Decimal("30.00"),
            stock_quantity=3,
            deleted_at=SEED_DELETED_AT,
        ),
        Product(id=TEA_SET_ID, name="Tea Set", price=Decimal("25.00"), currency="EUR", stock_quantity=10),
        User(id=DAVE_ID, email="dave@example.com", name="Dave"),
        sample_card(DAVE_CARD_ID, DAVE_ID, "tok_test_dave_visa", PaymentMethodType.CREDIT, "4444"),
        Cart(id=DAVE_EMPTY_CART_ID, user_id=DAVE_ID),
        Cart(id=DAVE_CHECKED_OUT_CART_ID, user_id=DAVE_ID, status=CartStatus.CHECKED_OUT.value),
        Cart(id=DAVE_ABANDONED_CART_ID, user_id=DAVE_ID, status=CartStatus.ABANDONED.value),
        Cart(id=DAVE_DELETED_CART_ID, user_id=DAVE_ID, deleted_at=SEED_DELETED_AT),
        Cart(id=DAVE_DELETED_PRODUCT_CART_ID, user_id=DAVE_ID),
        sample_item("f0000000-0000-0000-0000-000000000001", DAVE_DELETED_PRODUCT_CART_ID, KETTLE_ID, 1, "45.00"),
        sample_item("f0000000-0000-0000-0000-000000000002", DAVE_DELETED_PRODUCT_CART_ID, LAMP_ID, 1, "30.00"),
        Cart(id=DAVE_MIXED_CURRENCY_CART_ID, user_id=DAVE_ID),
        sample_item("f0000000-0000-0000-0000-000000000003", DAVE_MIXED_CURRENCY_CART_ID, KETTLE_ID, 1, "45.00"),
        sample_item("f0000000-0000-0000-0000-000000000004", DAVE_MIXED_CURRENCY_CART_ID, TEA_SET_ID, 1, "25.00"),
        Cart(id=DAVE_NO_STOCK_CART_ID, user_id=DAVE_ID),
        # The blanket has 5 in stock.
        sample_item("f0000000-0000-0000-0000-000000000005", DAVE_NO_STOCK_CART_ID, BLANKET_ID, 6, "89.99"),
    ]


def sample_card(
    id: uuid.UUID,
    user_id: uuid.UUID,
    provider_token: str,
    type: PaymentMethodType,
    last_four: str,
) -> UserPaymentMethod:
    """One of the extra sample cards."""
    return UserPaymentMethod(
        id=id,
        user_id=user_id,
        provider_token=provider_token,
        type=type.value,
        last_four=last_four,
    )


def sample_item(
    id: str, cart_id: uuid.UUID, product_id: uuid.UUID, quantity: int, unit_price: str
) -> CartItem:
    """One of Dave's sample cart items."""
    return CartItem(
        id=uuid.UUID(id),
        cart_id=cart_id,
        product_id=product_id,
        quantity=quantity,
        unit_price=Decimal(unit_price),
    )


@click.command("seed")
@with_appcontext
def seed() -> None:
    """
    Insert the sample data from quick-start.sql, skipping records that already exist.

    Each insert is logged, like the changes made by the repositories.
    """
    session = get_session()
    records = sample_data()
    inserted = 0

    for record in records:
        # session.get also finds soft-deleted rows, so the id is never inserted twice.
        if session.get(type(record), record.id) is None:
            session.add(record)
            session.flush()
            session.add(
                action_logger.db_change_entry(
                    record.__tablename__,
                    record.id,
                    ChangeOperation.INSERT,
                    before=None,
                    after=record.column_values(),
                )
            )
            inserted += 1

    session.commit()

    click.echo(f"{inserted} records inserted, {len(records) - inserted} already existed.")


mock_provider_cli = AppGroup("mock-provider", help="Commands of the mock payment provider.")


@mock_provider_cli.command("settle")
def settle() -> None:
    """
    Send the result of every pending charge to the webhook, like the real
    provider would do some time after accepting the charge.

    The result depends on the card token (see MockPaymentProvider). The call
    goes through the real API, so it is validated, signed and logged.
    """
    with PaymentRepository(get_session()) as payments:
        charges = [
            (
                payment.id,
                payment.provider_transaction_id,
                payment.payment_method.provider_token,
                payment.payment_type,
            )
            for payment in payments.get_pending()
            # Without a transaction id the charge is still being started.
            if payment.provider_transaction_id is not None
        ]

    client = current_app.test_client()

    for payment_id, transaction_id, provider_token, payment_type in charges:
        result, failure_reason = MockPaymentProvider.settlement(provider_token, payment_type)
        body = json.dumps({
            "payment_id": str(payment_id),
            "provider_transaction_id": transaction_id,
            "status": result.value,
            "failure_reason": failure_reason,
        }).encode()

        response = client.post(
            "/payments/webhook",
            data=body,
            content_type="application/json",
            headers={SIGNATURE_HEADER: sign(body, current_app.config["WEBHOOK_SECRET"])},
        )

        click.echo(f"{payment_id}: {result.value} -> HTTP {response.status_code}")

    click.echo(f"{len(charges)} pending charges settled.")
