"""
Keys whose values are never saved in the logs.

Matching is case-insensitive and applies at any depth of a payload.
"""

SENSITIVE_KEYS = frozenset({
    "provider_token",
    "token",
    "password",
    "authorization",
    "cookie",
    "card_number",
    "cvv",
})

MASK = "***"
