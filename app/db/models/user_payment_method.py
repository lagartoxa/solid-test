"""
UserPaymentMethod model - payment methods a user has saved.
"""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CHAR, Boolean, ForeignKey, Index, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.constants import PaymentMethodType
from app.db.models.base import BaseModel, enum_check

if TYPE_CHECKING:
    from app.db.models.user import User


class UserPaymentMethod(BaseModel):
    """
    A saved payment method.

    provider_token is the token from the external payment provider. The real
    card number is not stored - the provider holds it.
    """

    __tablename__ = "user_payment_methods"
    __table_args__ = (
        Index("idx_user_payment_methods_user_id", "user_id"),
        enum_check("type", PaymentMethodType, "user_payment_methods_type_check"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    provider_token: Mapped[str] = mapped_column(Text, nullable=False)
    # Credit or debit card (PaymentMethodType).
    type: Mapped[str] = mapped_column(Text, nullable=False)
    last_four: Mapped[Optional[str]] = mapped_column(CHAR(4))
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )

    user: Mapped["User"] = relationship(back_populates="payment_methods")
