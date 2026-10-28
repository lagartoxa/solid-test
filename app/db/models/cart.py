"""
Cart models - shopping carts and the products added to them.
"""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.constants import CartStatus
from app.db.models.base import BaseModel, VersionedBaseModel

if TYPE_CHECKING:
    from app.db.models.product import Product
    from app.db.models.user import User


class Cart(VersionedBaseModel):
    """
    A shopping cart. One cart is active per user at a time.

    Versioned so every status change is kept in carts_history (for debugging).
    """

    __tablename__ = "carts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'checked_out', 'abandoned')",
            name="carts_status_check",
        ),
        Index("idx_carts_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=CartStatus.ACTIVE.value
    )

    user: Mapped["User"] = relationship(back_populates="carts")
    items: Mapped[List["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(BaseModel):
    """
    A product added to a cart.

    unit_price is stored on the row so the price at checkout is stable
    if the product price changes later.
    """

    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="cart_items_quantity_check"),
        Index("idx_cart_items_cart_id", "cart_id"),
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    cart: Mapped["Cart"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
