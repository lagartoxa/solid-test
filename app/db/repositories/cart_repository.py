"""
Cart repository for cart-related database operations.
"""

from app.db.models.cart import Cart
from app.db.repositories.base import VersionedBaseRepository
from app.schemas.cart import CartCreate, CartUpdate


class CartRepository(VersionedBaseRepository[Cart, CartCreate, CartUpdate]):
    """Repository for Cart model. Carts are versioned: every change is kept in carts_history."""

    model_class = Cart
