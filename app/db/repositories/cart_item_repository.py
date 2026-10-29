"""
CartItem repository for cart item database operations.
"""

import uuid
from typing import List

from app.db.models.cart import CartItem
from app.db.repositories.base import BaseRepository
from app.schemas.cart import CartItemCreate, CartItemUpdate


class CartItemRepository(BaseRepository[CartItem, CartItemCreate, CartItemUpdate]):
    """Repository for CartItem model."""

    model_class = CartItem

    def get_by_cart(self, cart_id: uuid.UUID) -> List[CartItem]:
        """
        Get the items of a cart.

        Args:
            cart_id: Cart id

        Returns:
            List of cart items
        """
        return list(self.session.scalars(self._query().where(CartItem.cart_id == cart_id)))
