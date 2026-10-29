"""
UserPaymentMethod schemas - input for the user payment method repository.
"""

import uuid
from typing import Optional

from pydantic import BaseModel, Field

from app.db.constants import PaymentMethodType


class UserPaymentMethodCreate(BaseModel):
    user_id: uuid.UUID
    provider_token: str
    type: PaymentMethodType
    last_four: Optional[str] = Field(default=None, min_length=4, max_length=4)
    is_default: bool = False


class UserPaymentMethodUpdate(BaseModel):
    last_four: Optional[str] = Field(default=None, min_length=4, max_length=4)
    is_default: Optional[bool] = None
