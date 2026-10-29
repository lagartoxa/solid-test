"""
End to end with the mock provider: start a payment, then `flask mock-provider settle`
sends the provider's result through the webhook.
"""

import pytest
from sqlalchemy import select

from app.db.constants import CartStatus, LogAction, PaymentMethodType, PaymentStatus
from app.db.models import Cart, Log, Payment
from app.services.payment_provider import DECLINED_TOKEN
from tests.factories import SUCCESS_TOKEN, get_payment, make_shop, post_payment


def start_and_settle(app, client, db_session, token, type):
    shop = make_shop(db_session, token=token, type=type)
    started = post_payment(client, shop.cart.id, shop.method.id, shop.user.id)
    assert started.status_code == 202

    result = app.test_cli_runner().invoke(args=["mock-provider", "settle"])
    assert result.exit_code == 0, result.output

    return shop, get_payment(client, shop.cart.id, started.json["id"], shop.user.id).json


@pytest.mark.parametrize("type", [PaymentMethodType.CREDIT, PaymentMethodType.DEBIT])
def test_accepted_charge_succeeds(app, client, db_session, type):
    shop, payment = start_and_settle(app, client, db_session, SUCCESS_TOKEN, type)

    assert payment["status"] == PaymentStatus.SUCCEEDED.value
    assert db_session.get(Cart, shop.cart.id).status == CartStatus.CHECKED_OUT.value


@pytest.mark.parametrize(
    "type, reason",
    [
        (PaymentMethodType.DEBIT, "insufficient funds"),
        (PaymentMethodType.CREDIT, "credit limit exceeded"),
    ],
)
def test_declined_charge_fails_with_reason_by_card_type(app, client, db_session, type, reason):
    shop, payment = start_and_settle(app, client, db_session, DECLINED_TOKEN, type)

    assert payment["status"] == PaymentStatus.FAILED.value
    assert payment["failure_reason"] == reason
    assert db_session.get(Cart, shop.cart.id).status == CartStatus.ACTIVE.value


def test_settlement_goes_through_the_api_and_is_logged(app, client, db_session):
    start_and_settle(app, client, db_session, SUCCESS_TOKEN, PaymentMethodType.CREDIT)

    webhook_logs = list(
        db_session.scalars(
            select(Log).where(
                Log.action == LogAction.API_REQUEST.value, Log.target == "POST /payments/webhook"
            )
        )
    )
    assert [log.status_code for log in webhook_logs] == [200]


def test_nothing_to_settle(app, db_session):
    result = app.test_cli_runner().invoke(args=["mock-provider", "settle"])

    assert result.exit_code == 0
    assert "0 pending charges settled." in result.output
    assert list(db_session.scalars(select(Payment))) == []
