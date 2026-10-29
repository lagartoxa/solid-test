"""
Payment provider - the external service that charges the cards.

PaymentProvider is the interface the payment service uses. MockPaymentProvider
replaces the real provider: the card token decides the outcome, like the test
cards of real providers' sandboxes.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.db.constants import PaymentMethodType, ProviderResult

# Mock card tokens with a special outcome. Any other token succeeds.
REFUSED_TOKEN = "tok_refused"
UNAVAILABLE_TOKEN = "tok_unavailable"
DECLINED_TOKEN = "tok_declined"

REFUSED_REASON = "invalid card token"
UNAVAILABLE_REASON = "payment provider is unavailable"
DECLINE_REASONS = {
    PaymentMethodType.DEBIT.value: "insufficient funds",
    PaymentMethodType.CREDIT.value: "credit limit exceeded",
}


@dataclass(frozen=True)
class ChargeRequest:
    """What we send to the provider to start a charge."""

    payment_id: uuid.UUID
    provider_token: str
    amount: Decimal
    currency: str


class ChargeRefused(Exception):
    """The provider answered and refused the charge (e.g. invalid card token)."""


class ProviderUnavailable(Exception):
    """The provider is unreachable, timed out or answered with an error."""


class PaymentProvider(ABC):
    """Interface of the payment provider."""

    @abstractmethod
    def start_charge(self, request: ChargeRequest) -> str:
        """
        Start a charge. The result arrives later through the webhook.

        Args:
            request: Charge to start

        Returns:
            Provider transaction id

        Raises:
            ChargeRefused: the provider refused the charge
            ProviderUnavailable: the provider could not be reached or failed
        """


class MockPaymentProvider(PaymentProvider):
    """
    Mock provider. The card token decides the outcome:

    - tok_refused: refused when the charge starts.
    - tok_unavailable: the provider fails when the charge starts.
    - tok_declined: accepted, then settled as failed (reason by card type).
    - any other token: accepted, then settled as succeeded.
    """

    def start_charge(self, request: ChargeRequest) -> str:
        """Start a charge (see the class docstring for the token rules)."""
        if request.provider_token == REFUSED_TOKEN:
            raise ChargeRefused(REFUSED_REASON)

        if request.provider_token == UNAVAILABLE_TOKEN:
            raise ProviderUnavailable(UNAVAILABLE_REASON)

        return f"mock_tx_{uuid.uuid4().hex}"

    @staticmethod
    def settlement(provider_token: str, payment_type: str) -> tuple[ProviderResult, Optional[str]]:
        """
        Final result of an accepted charge, reported later through the webhook.

        Args:
            provider_token: Card token
            payment_type: credit or debit

        Returns:
            Result and failure reason (None when it succeeded)
        """
        if provider_token == DECLINED_TOKEN:
            return ProviderResult.FAILED, DECLINE_REASONS[payment_type]

        return ProviderResult.SUCCEEDED, None
