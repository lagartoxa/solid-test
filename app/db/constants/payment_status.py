"""
Payment status values.
"""

from enum import Enum


class PaymentStatus(str, Enum):
    """
    Payment status values.

    - pending: the charge was started; the provider's result is not known yet.
    - succeeded: the provider charged the card.
    - failed: the provider refused or could not charge the card.
    """

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# A cart can have only one payment in these statuses.
ACTIVE_PAYMENT_STATUSES = (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED)
