"""
Base model and mixins for all database models.

This module provides:
- Base declarative class for all models
- TimestampMixin: created_at and updated_at
- SoftDeleteMixin: soft delete pattern with deleted_at
- BaseModel: the class every table inherits from
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models using SQLAlchemy 2.0 declarative base."""


class TimestampMixin:
    """
    Timestamp fields for created_at and updated_at.

    Both are set by the database on insert. updated_at is refreshed by
    SQLAlchemy on every ORM update, using clock_timestamp() instead of now()
    because now() returns the start time of the transaction.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        sort_order=1,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.clock_timestamp(),
        sort_order=1,
    )


class SoftDeleteMixin:
    """
    Soft delete pattern using a deleted_at timestamp.

    - Active records: WHERE deleted_at IS NULL
    - Deleted records: WHERE deleted_at IS NOT NULL
    """

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        sort_order=1,
    )

    @hybrid_property
    def deleted(self) -> bool:
        """Returns True if record is soft-deleted, False otherwise."""
        return self.deleted_at is not None

    @deleted.expression
    def deleted(cls):
        """SQL expression for deleted hybrid property."""
        return cls.deleted_at.is_not(None)

    def soft_delete(self) -> None:
        """Mark this record as deleted at the current time."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None


class BaseModel(Base, TimestampMixin, SoftDeleteMixin):
    """
    Base model for all database tables.

    All models inherit from this class to get:
    - UUID primary key (id)
    - created_at / updated_at timestamps
    - Soft delete capability (deleted_at)
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
        sort_order=-1,
    )

    def __repr__(self) -> str:
        """String representation of model instance."""
        return f"<{self.__class__.__name__}(id={self.id})>"
