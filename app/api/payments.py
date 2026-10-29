"""
Payment endpoints: start a payment, read its status and receive the
provider's result (webhook). See docs/payment-requirements.md.
"""

from http import HTTPStatus

from flask import current_app, request
from flask_openapi3 import APIBlueprint, Tag

from app.db.models import Payment
from app.schemas.payment import (
    CartPath,
    ErrorResponse,
    PaymentPath,
    PaymentResponse,
    StartPaymentBody,
    UserHeader,
    WebhookBody,
    WebhookHeader,
)
from app.services.errors import ErrorCode, InvalidSignatureError
from app.services.payment_service import build_payment_service
from app.services.webhook_signature import SIGNATURE_HEADER, is_valid

payments_bp = APIBlueprint("payments", __name__, abp_tags=[Tag(name="Payments")])
webhook_bp = APIBlueprint(
    "payment_webhook", __name__, abp_tags=[Tag(name="Payment provider webhook")]
)


def payment_response(payment: Payment) -> dict:
    """JSON body of a payment."""
    return PaymentResponse.model_validate(payment).model_dump(mode="json")


@payments_bp.post(
    "/carts/<cart_id>/payments",
    summary="Start the payment of a cart",
    description="Reserves the stock and starts the charge. The result arrives "
    "later; read it with the GET endpoint.",
    responses={
        HTTPStatus.ACCEPTED: PaymentResponse,
        HTTPStatus.PAYMENT_REQUIRED: ErrorResponse,
        HTTPStatus.NOT_FOUND: ErrorResponse,
        HTTPStatus.CONFLICT: ErrorResponse,
        HTTPStatus.BAD_GATEWAY: ErrorResponse,
    },
)
def start_payment(path: CartPath, header: UserHeader, body: StartPaymentBody):
    payment = build_payment_service().start_payment(
        path.cart_id, header.user_id, body.payment_method_id
    )

    return payment_response(payment), HTTPStatus.ACCEPTED


@payments_bp.get(
    "/carts/<cart_id>/payments/<payment_id>",
    summary="Read the status of a payment",
    responses={HTTPStatus.OK: PaymentResponse, HTTPStatus.NOT_FOUND: ErrorResponse},
)
def get_payment(path: PaymentPath, header: UserHeader):
    payment = build_payment_service().get_payment(path.cart_id, header.user_id, path.payment_id)

    return payment_response(payment), HTTPStatus.OK


@webhook_bp.before_request
def verify_signature() -> None:
    """
    Reject webhook calls not signed with the shared secret.

    Runs before the body is validated, so an unsigned call never gets past 401.
    """
    if not is_valid(
        request.get_data(),
        request.headers.get(SIGNATURE_HEADER),
        current_app.config["WEBHOOK_SECRET"],
    ):
        raise InvalidSignatureError(
            ErrorCode.INVALID_SIGNATURE, "The webhook signature is missing or invalid."
        )


# header is only declared so Swagger documents X-Signature; verify_signature checks it.
@webhook_bp.post(
    "/payments/webhook",
    summary="Result of a charge, sent by the payment provider",
    responses={
        HTTPStatus.OK: PaymentResponse,
        HTTPStatus.UNAUTHORIZED: ErrorResponse,
        HTTPStatus.NOT_FOUND: ErrorResponse,
        HTTPStatus.CONFLICT: ErrorResponse,
    },
)
def payment_webhook(header: WebhookHeader, body: WebhookBody):
    payment = build_payment_service().apply_provider_result(body)

    return payment_response(payment), HTTPStatus.OK
