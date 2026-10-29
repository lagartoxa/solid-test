"""
Payment method type values.
"""

from enum import Enum


class PaymentMethodType(str, Enum):
    """The kind of card of a payment method."""

    CREDIT = "credit"
    DEBIT = "debit"
