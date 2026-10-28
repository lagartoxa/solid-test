"""
Flask CLI commands.
"""

import uuid
from decimal import Decimal

import click
from flask import Flask
from flask.cli import with_appcontext

from app.db.constants import ChangeOperation
from app.db.models import BaseModel, Cart, CartItem, Product, User, UserPaymentMethod
from app.db.session import get_session
from app.log.action_logger import action_logger

ALICE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
BOB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
KETTLE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BLANKET_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
MUG_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
ALICE_CART_ID = uuid.UUID("c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1")
ALICE_CART_KETTLE_ID = uuid.UUID("d1d1d1d1-d1d1-d1d1-d1d1-d1d1d1d1d1d1")
ALICE_CART_MUG_ID = uuid.UUID("d2d2d2d2-d2d2-d2d2-d2d2-d2d2d2d2d2d2")
ALICE_CARD_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def register_cli(app: Flask) -> None:
    """Register the CLI commands on the app."""
    app.cli.add_command(seed)


def sample_data() -> list[BaseModel]:
    """
    Sample data from quick-start.sql, in insertion order (parents first).

    Every record has a fixed id, so the seed can tell if it was already inserted.
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
            last_four="4242",
            is_default=True,
        ),
    ]


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
