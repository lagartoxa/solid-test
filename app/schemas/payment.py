"""
Payment schemas - repository input and API request/response bodies.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.constants import PaymentMethodType, PaymentStatus, ProviderResult
from app.log.action_logger import USER_ID_HEADER
from app.services.errors import ErrorCode
from app.services.webhook_signature import SIGNATURE_HEADER

# ============================================================================
# REPOSITORY INPUT
# ============================================================================


class PaymentCreate(BaseModel):
    cart_id: uuid.UUID
    user_id: uuid.UUID
    payment_method_id: uuid.UUID
    payment_type: PaymentMethodType
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


class PaymentUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    provider_transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None


# ============================================================================
# API INPUT
# ============================================================================


class UserHeader(BaseModel):
    """The caller, from the User-Id header."""

    user_id: uuid.UUID = Field(alias=USER_ID_HEADER, description="Id of the user making the request")


class CartPath(BaseModel):
    cart_id: uuid.UUID


class PaymentPath(BaseModel):
    cart_id: uuid.UUID
    payment_id: uuid.UUID


class StartPaymentBody(BaseModel):
    payment_method_id: uuid.UUID = Field(
        description="Payment method chosen by the user (required: the API never picks one)"
    )


class WebhookHeader(BaseModel):
    """The signature, from the X-Signature header."""

    x_signature: Optional[str] = Field(
        default=None,
        alias=SIGNATURE_HEADER,
        description="HMAC-SHA256 of the raw body with the shared secret",
    )


class WebhookBody(BaseModel):
    """Result of a charge, sent by the payment provider."""

    payment_id: uuid.UUID
    provider_transaction_id: str
    status: ProviderResult
    failure_reason: Optional[str] = None

    @model_validator(mode="after")
    def failure_reason_when_failed(self) -> "WebhookBody":
        """A failed charge must say why."""
        if self.status is ProviderResult.FAILED and not self.failure_reason:
            raise ValueError("failure_reason is required when status is failed")

        return self


# ============================================================================
# API RESPONSES
# ============================================================================


class PaymentResponse(BaseModel):
    """A payment, as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cart_id: uuid.UUID
    payment_method_id: uuid.UUID
    payment_type: PaymentMethodType
    amount: Decimal
    currency: str
    status: PaymentStatus
    provider_transaction_id: Optional[str]
    failure_reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class ErrorResponse(BaseModel):
    """A business error: a stable code and a message."""

    error: ErrorCode
    message: str
