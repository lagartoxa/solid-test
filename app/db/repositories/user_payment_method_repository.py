"""
UserPaymentMethod repository for saved payment method database operations.
"""

from app.db.models.user_payment_method import UserPaymentMethod
from app.db.repositories.base import BaseRepository
from app.schemas.user_payment_method import (
    UserPaymentMethodCreate,
    UserPaymentMethodUpdate,
)


class UserPaymentMethodRepository(
    BaseRepository[UserPaymentMethod, UserPaymentMethodCreate, UserPaymentMethodUpdate]
):
    """Repository for UserPaymentMethod model."""

    model_class = UserPaymentMethod
