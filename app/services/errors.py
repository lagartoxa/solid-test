"""
Business errors returned by the API.

Each error has an HTTP status, a stable code and a message. The API turns
any ApiError into {"error": code, "message": message} with that status.
"""

from enum import Enum


class ErrorCode(str, Enum):
    """Stable codes of the business errors, for clients and for the logs."""

    USER_NOT_FOUND = "user_not_found"
    CART_NOT_FOUND = "cart_not_found"
    PAYMENT_NOT_FOUND = "payment_not_found"
    CART_NOT_ACTIVE = "cart_not_active"
    ACTIVE_PAYMENT_EXISTS = "active_payment_exists"
    NO_PAYMENT_METHOD = "no_payment_method"
    PAYMENT_METHOD_NOT_FOUND = "payment_method_not_found"
    CART_EMPTY = "cart_empty"
    PRODUCT_UNAVAILABLE = "product_unavailable"
    MIXED_CURRENCIES = "mixed_currencies"
    INSUFFICIENT_STOCK = "insufficient_stock"
    PAYMENT_NOT_PENDING = "payment_not_pending"
    CONCURRENT_UPDATE = "concurrent_update"
    PAYMENT_REFUSED = "payment_refused"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_SIGNATURE = "invalid_signature"


class ApiError(Exception):
    """Base class: an error with an HTTP status, a code and a message."""

    status_code = 500

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(ApiError):
    """A resource doesn't exist, is deleted or belongs to another user."""

    status_code = 404


class ConflictError(ApiError):
    """The request conflicts with the current state of the data."""

    status_code = 409


class PaymentRefusedError(ApiError):
    """The payment provider refused the charge."""

    status_code = 402


class ProviderUnavailableError(ApiError):
    """The payment provider is unreachable or failed."""

    status_code = 502


class InvalidSignatureError(ApiError):
    """A webhook call is not signed with the shared secret."""

    status_code = 401
