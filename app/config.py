"""
Application configuration loaded from environment variables.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Default configuration."""

    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://shop:shop@localhost:5432/shop"
    )
    TESTING = False


class TestingConfig(Config):
    """Configuration used by the automated tests."""

    DATABASE_URL = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://shop:shop@localhost:5432/shop_test"
    )
    TESTING = True
