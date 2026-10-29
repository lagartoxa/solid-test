"""
UserPaymentMethod repository for saved payment method database operations.
"""

import uuid
from typing import Optional

from sqlalchemy import select

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

    def has_any_for_user(self, user_id: uuid.UUID) -> bool:
        """
        Check if a user has at least one (not deleted) payment method.

        Args:
            user_id: User id

        Returns:
            True if the user has a payment method
        """
        query = self._query().where(UserPaymentMethod.user_id == user_id)

        return self.session.scalar(select(query.exists()))

    def get_for_user(self, id: uuid.UUID, user_id: uuid.UUID) -> Optional[UserPaymentMethod]:
        """
        Get a payment method only if it belongs to the user.

        Args:
            id: Payment method id
            user_id: User id

        Returns:
            Payment method or None if not found, deleted or another user's
        """
        query = self._query().where(
            UserPaymentMethod.id == id, UserPaymentMethod.user_id == user_id
        )

        return self.session.scalars(query).first()
