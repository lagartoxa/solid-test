"""
Signature of the payment provider's webhook calls.

The provider signs the raw body with a secret shared with us (HMAC-SHA256),
so nobody else can call the webhook and mark a payment as paid.
"""

import hashlib
import hmac
from typing import Optional

SIGNATURE_HEADER = "X-Signature"


def sign(body: bytes, secret: str) -> str:
    """
    Signature of a webhook body.

    Args:
        body: Raw request body
        secret: Shared secret

    Returns:
        Hex HMAC-SHA256 of the body
    """
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def is_valid(body: bytes, signature: Optional[str], secret: str) -> bool:
    """
    Check a webhook signature, in constant time.

    Args:
        body: Raw request body
        signature: Signature received (None when the header is missing)
        secret: Shared secret

    Returns:
        True if the signature matches the body
    """
    return signature is not None and hmac.compare_digest(sign(body, secret), signature)
