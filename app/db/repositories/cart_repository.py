"""
Cart repository for cart-related database operations.
"""

from app.db.models.cart import Cart
from app.db.repositories.base import BaseRepository
from app.schemas.cart import CartCreate, CartUpdate


class CartRepository(BaseRepository[Cart, CartCreate, CartUpdate]):
    """Repository for Cart model."""

    model_class = Cart
