"""
Payment total calculation service.

It is an existing external service: it tells us what to charge for a cart, as
line items. StubTotalCalculationService replaces it here and reads the cart
items from our database.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.repositories import CartItemRepository


@dataclass(frozen=True)
class LineItem:
    """One product to charge: quantity x unit_price."""

    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal


class TotalCalculationService(ABC):
    """Interface of the payment total calculation service."""

    @abstractmethod
    def get_line_items(self, cart_id: uuid.UUID) -> list[LineItem]:
        """
        Line items to charge for a cart.

        Args:
            cart_id: Cart to pay

        Returns:
            Line items (empty for an empty cart)
        """


class StubTotalCalculationService(TotalCalculationService):
    """Stub: the line items are the cart items, at the price stored on them."""

    def __init__(self, session: Session):
        self.session = session

    def get_line_items(self, cart_id: uuid.UUID) -> list[LineItem]:
        """Line items from the cart items (see TotalCalculationService)."""
        with CartItemRepository(self.session) as cart_items:
            return [
                LineItem(item.product_id, item.quantity, item.unit_price)
                for item in cart_items.get_by_cart(cart_id)
            ]
