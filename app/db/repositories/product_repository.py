"""
Product repository for product-related database operations.
"""

from app.db.models.product import Product
from app.db.repositories.base import BaseRepository
from app.schemas.product import ProductCreate, ProductUpdate


class ProductRepository(BaseRepository[Product, ProductCreate, ProductUpdate]):
    """Repository for Product model."""

    model_class = Product
