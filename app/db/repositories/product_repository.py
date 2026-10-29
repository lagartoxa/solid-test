"""
Product repository for product-related database operations.
"""

import uuid
from typing import Iterable

from app.db.models.product import Product
from app.db.repositories.base import BaseRepository
from app.schemas.product import ProductCreate, ProductUpdate


class ProductRepository(BaseRepository[Product, ProductCreate, ProductUpdate]):
    """Repository for Product model."""

    model_class = Product

    def get_many_for_update(self, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Product]:
        """
        Get and lock several products, including soft-deleted ones.

        Rows are locked in id order, so two requests locking the same products
        can't deadlock.

        Args:
            ids: Product ids

        Returns:
            Products by id (missing ids are left out)
        """
        query = (
            self._query(include_deleted=True)
            .where(Product.id.in_(list(ids)))
            .order_by(Product.id)
            .with_for_update()
        )

        return {product.id: product for product in self.session.scalars(query)}
