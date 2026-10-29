"""
Payment repository for payment database operations.
"""

import uuid
from typing import List, Optional

from sqlalchemy.orm import joinedload

from app.db.constants import ACTIVE_PAYMENT_STATUSES, PaymentStatus
from app.db.models.payment import Payment
from app.db.repositories.base import VersionedBaseRepository
from app.schemas.payment import PaymentCreate, PaymentUpdate


class PaymentRepository(VersionedBaseRepository[Payment, PaymentCreate, PaymentUpdate]):
    """Repository for Payment model. Payments are versioned: every change is kept in payments_history."""

    model_class = Payment

    def get_active_for_cart(self, cart_id: uuid.UUID) -> Optional[Payment]:
        """
        Get the pending or succeeded payment of a cart (there is at most one).

        Args:
            cart_id: Cart id

        Returns:
            Active payment or None
        """
        query = self._query().where(
            Payment.cart_id == cart_id,
            Payment.status.in_([status.value for status in ACTIVE_PAYMENT_STATUSES]),
        )

        return self.session.scalars(query).first()

    def get_for_cart(self, id: uuid.UUID, cart_id: uuid.UUID) -> Optional[Payment]:
        """
        Get a payment only if it belongs to the cart.

        Args:
            id: Payment id
            cart_id: Cart id

        Returns:
            Payment or None if not found, deleted or of another cart
        """
        query = self._query().where(Payment.id == id, Payment.cart_id == cart_id)

        return self.session.scalars(query).first()

    def get_pending(self) -> List[Payment]:
        """
        Get the pending payments with their payment method loaded, oldest first.

        Returns:
            List of pending payments
        """
        query = (
            self._query()
            .where(Payment.status == PaymentStatus.PENDING.value)
            .options(joinedload(Payment.payment_method))
            .order_by(Payment.created_at)
        )

        return list(self.session.scalars(query))
