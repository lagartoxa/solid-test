"""
CartItem repository for cart item database operations.
"""

from app.db.models.cart import CartItem
from app.db.repositories.base import BaseRepository
from app.schemas.cart import CartItemCreate, CartItemUpdate


class CartItemRepository(BaseRepository[CartItem, CartItemCreate, CartItemUpdate]):
    """Repository for CartItem model."""

    model_class = CartItem
