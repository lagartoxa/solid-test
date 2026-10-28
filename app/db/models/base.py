"""
Base model and mixins for all database models.

This module provides:
- Base declarative class for all models
- TimestampMixin: created_at and updated_at
- SoftDeleteMixin: soft delete pattern with deleted_at
- BaseModel: the class every table inherits from
- VersionedBaseModel: BaseModel that also keeps the history of every change
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Identity,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.db.constants import HistoryOperation

# Columns of a versioned table that are not copied to its history table:
# changed_at in the history row already says when the change happened.
HISTORY_EXCLUDED_COLUMNS = {"created_at", "updated_at"}


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


class VersionedBaseModel(BaseModel):
    """
    Base model for tables that keep the history of every change.

    To version a table, inherit from this class instead of BaseModel and
    generate a migration. Each subclass gets:
    - version: 1 on insert, +1 on every update. It is also SQLAlchemy's
      version_id_col, so updating a stale row raises StaleDataError instead
      of silently overwriting a concurrent change.
    - __history_class__: an ORM class for <tablename>_history, created
      automatically (e.g. Cart -> CartHistory, table carts_history) when the
      mappers are configured (app/db/models/__init__.py does it on import).

    History rows are written by the listener in app/db/repositories/versioning.py.
    """

    __abstract__ = True

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        sort_order=1,
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        """
        Use version as the optimistic lock column.

        eager_defaults loads server-generated values (e.g. the default status)
        right after the flush, so the history snapshot has every value.
        """
        return {"version_id_col": cls.__table__.c.version, "eager_defaults": True}

    @classmethod
    def __declare_first__(cls) -> None:
        """
        Create the history class before the mappers are configured.

        It can't be done when the class is defined: foreign key columns only
        get their type once the referenced table exists, which may be defined
        later (e.g. carts.user_id needs users).
        """
        cls.__history_class__ = _create_history_class(cls)


def _create_history_class(model: type[VersionedBaseModel]) -> type[Base]:
    """
    Create the ORM class and table that store the history of a versioned model.

    The history table copies every column of the model (except
    HISTORY_EXCLUDED_COLUMNS) with its type and nullability, but without
    foreign keys, unique constraints or defaults, so history rows survive
    anything that happens to the original rows. It is append-only, so it
    inherits Base, not BaseModel.

    Args:
        model: Mapped versioned model

    Returns:
        History ORM class
    """
    table_name = f"{model.__tablename__}_history"
    operations = ", ".join(f"'{operation.value}'" for operation in HistoryOperation)

    copied_columns = [
        Column(column.name, column.type, nullable=column.nullable)
        for column in model.__table__.columns
        if column.name not in HISTORY_EXCLUDED_COLUMNS
    ]

    table = Table(
        table_name,
        Base.metadata,
        Column("history_id", BigInteger, Identity(), primary_key=True),
        *copied_columns,
        Column("operation", Text, nullable=False),
        Column(
            "changed_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.clock_timestamp(),
        ),
        UniqueConstraint("id", "version", name=f"uq_{table_name}_id_version"),
        CheckConstraint(f"operation IN ({operations})", name=f"{table_name}_operation_check"),
    )

    return type(f"{model.__name__}History", (Base,), {"__table__": table})
