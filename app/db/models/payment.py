"""
Payment model - a payment of a cart.
"""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CHAR, CheckConstraint, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.constants import ACTIVE_PAYMENT_STATUSES, PaymentMethodType, PaymentStatus
from app.db.models.base import VersionedBaseModel, enum_check, sql_values

# Unique index: one pending or succeeded payment per cart.
ACTIVE_PAYMENT_INDEX = "uq_payments_cart_id_active"

if TYPE_CHECKING:
    from app.db.models.cart import Cart
    from app.db.models.user_payment_method import UserPaymentMethod


class Payment(VersionedBaseModel):
    """
    A payment of a cart, charged through the payment provider.

    Starts as pending; the provider's webhook makes it succeeded or failed.
    Versioned so every status change is kept in payments_history (for debugging).

    payment_type is copied from the payment method, so the payment keeps the
    type it was charged with even if the method changes later.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="payments_amount_check"),
        enum_check("status", PaymentStatus, "payments_status_check"),
        enum_check("payment_type", PaymentMethodType, "payments_payment_type_check"),
        Index("idx_payments_cart_id", "cart_id"),
        Index("idx_payments_user_id", "user_id"),
        # A cart can have only one pending or succeeded payment: no double charge.
        Index(
            ACTIVE_PAYMENT_INDEX,
            "cart_id",
            unique=True,
            postgresql_where=text(
                f"status IN ({sql_values(ACTIVE_PAYMENT_STATUSES)}) AND deleted_at IS NULL"
            ),
        ),
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("carts.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    payment_method_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_payment_methods.id"), nullable=False
    )
    payment_type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=PaymentStatus.PENDING.value
    )
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(Text)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)

    cart: Mapped["Cart"] = relationship()
    payment_method: Mapped["UserPaymentMethod"] = relationship()
