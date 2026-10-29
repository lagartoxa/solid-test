"""
Turns business and concurrency errors into JSON error responses.
"""

from http import HTTPStatus
from typing import Any

from flask import Flask
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.db.models.payment import ACTIVE_PAYMENT_INDEX
from app.log.request_logging import handle_unexpected_error
from app.schemas.payment import ErrorResponse
from app.services.errors import ApiError, ErrorCode


def register_error_handlers(app: Flask) -> None:
    """Register the error handlers on the app."""
    app.register_error_handler(ApiError, handle_api_error)
    app.register_error_handler(StaleDataError, handle_concurrent_update)
    app.register_error_handler(IntegrityError, handle_integrity_error)


def error_response(status: int, code: ErrorCode, message: str) -> tuple[dict, int]:
    """JSON body of a business error: {"error": code, "message": message}."""
    return ErrorResponse(error=code, message=message).model_dump(mode="json"), status


def handle_api_error(error: ApiError) -> tuple[dict, int]:
    """A business error raised by a service."""
    return error_response(error.status_code, error.code, error.message)


def handle_concurrent_update(error: StaleDataError) -> tuple[dict, int]:
    """Another request changed the same versioned record at the same time."""
    return error_response(
        HTTPStatus.CONFLICT,
        ErrorCode.CONCURRENT_UPDATE,
        "The data was changed by another request. Please try again.",
    )


def handle_integrity_error(error: IntegrityError) -> Any:
    """
    Two requests created a payment for the same cart at the same time: the
    unique index stopped the second one. Any other integrity error is unexpected.
    """
    if ACTIVE_PAYMENT_INDEX in str(error.orig):
        return error_response(
            HTTPStatus.CONFLICT,
            ErrorCode.ACTIVE_PAYMENT_EXISTS,
            "The cart already has a pending or succeeded payment.",
        )

    return handle_unexpected_error(error)
