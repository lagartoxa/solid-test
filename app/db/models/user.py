"""
User model - users of the shop.
"""

from typing import TYPE_CHECKING, List

from sqlalchemy import Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import BaseModel

if TYPE_CHECKING:
    from app.db.models.cart import Cart
    from app.db.models.user_payment_method import UserPaymentMethod


class User(BaseModel):
    """A user of the shop."""

    __tablename__ = "users"
    __table_args__ = (
        # Unique among active users only, so a soft-deleted email can be reused.
        Index(
            "uq_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    carts: Mapped[List["Cart"]] = relationship(back_populates="user")
    payment_methods: Mapped[List["UserPaymentMethod"]] = relationship(
        back_populates="user"
    )
