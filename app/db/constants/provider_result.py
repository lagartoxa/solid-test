"""
Payment provider result values.
"""

from enum import Enum


class ProviderResult(str, Enum):
    """Result of a charge, reported by the payment provider through the webhook."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
