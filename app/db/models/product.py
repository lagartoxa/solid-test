"""
Product model - the physical products the shop sells.
"""

from decimal import Decimal

from sqlalchemy import CHAR, CheckConstraint, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import BaseModel


class Product(BaseModel):
    """A physical product the shop sells."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="products_price_check"),
        CheckConstraint("stock_quantity >= 0", name="products_stock_quantity_check"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        CHAR(3), nullable=False, server_default="USD"
    )
    stock_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
