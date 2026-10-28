"""
Product schemas - input for the product repository.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str
    price: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    stock_quantity: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    stock_quantity: Optional[int] = Field(default=None, ge=0)
