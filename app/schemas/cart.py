"""
Cart schemas - input for the cart and cart item repositories.
"""

import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.db.constants import CartStatus


class CartCreate(BaseModel):
    user_id: uuid.UUID
    status: CartStatus = CartStatus.ACTIVE


class CartUpdate(BaseModel):
    status: Optional[CartStatus] = None


class CartItemCreate(BaseModel):
    cart_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class CartItemUpdate(BaseModel):
    quantity: Optional[int] = Field(default=None, gt=0)
    unit_price: Optional[Decimal] = Field(default=None, ge=0)
