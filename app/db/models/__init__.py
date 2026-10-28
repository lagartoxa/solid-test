"""
Models module - all model classes.
"""

from sqlalchemy.orm import configure_mappers

from app.db.models.base import Base, BaseModel, VersionedBaseModel
from app.db.models.cart import Cart, CartItem
from app.db.models.product import Product
from app.db.models.user import User
from app.db.models.user_payment_method import UserPaymentMethod

# Configure the mappers now that every model is imported. This creates the
# history tables of versioned models, so they exist for Alembic and the app.
configure_mappers()

CartHistory = Cart.__history_class__

__all__ = [
    "Base",
    "BaseModel",
    "VersionedBaseModel",
    "User",
    "Product",
    "Cart",
    "CartHistory",
    "CartItem",
    "UserPaymentMethod",
]
