"""
Cart status values.
"""

from enum import Enum


class CartStatus(str, Enum):
    """
    Cart status values.

    - active: the user can still add or remove products.
    - checked_out: the user paid for this cart.
    - abandoned: the user did not pay and started a new cart.
    """

    ACTIVE = "active"
    CHECKED_OUT = "checked_out"
    ABANDONED = "abandoned"
