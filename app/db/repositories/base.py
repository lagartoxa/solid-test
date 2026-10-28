"""
Base repository with generic CRUD operations and context manager protocol.
"""

import uuid
from typing import Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models.base import Base, BaseModel, VersionedBaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)
VersionedModelType = TypeVar("VersionedModelType", bound=VersionedBaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=PydanticBaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=PydanticBaseModel)

# Keys in session.info used to share the transaction between nested repositories.
NESTING_DEPTH_KEY = "repository_nesting_depth"
FAILED_KEY = "repository_failed"


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Base repository implementing generic CRUD operations with context manager protocol.

    All repositories must inherit from this class and set the model_class attribute.

    Usage:
        with MyRepository(session) as repo:
            item = repo.create(schema)

    To use more than one repository in the same transaction, nest the with
    statements. Only the outermost one commits (or rolls back) and closes the
    session:
        with UserRepository(session) as users:
            with CartRepository(session) as carts:
                ...
    """

    model_class: Type[ModelType] = None

    def __init__(self, session: Session):
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
        if self.model_class is None:
            raise NotImplementedError("model_class must be set in child class")

        self.session = session

    def __enter__(self):
        """Context manager entry - registers one more nesting level on the session."""
        info = self.session.info
        info[NESTING_DEPTH_KEY] = info.get(NESTING_DEPTH_KEY, 0) + 1

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit - finishes the transaction and closes the session.

        Nested repositories only record a failure. The outermost one rolls back
        if any level failed, commits otherwise, and always closes the session,
        returning the connection to the pool.
        """
        info = self.session.info
        info[NESTING_DEPTH_KEY] -= 1

        if exc_type is not None:
            info[FAILED_KEY] = True

        if info[NESTING_DEPTH_KEY] > 0:
            return False

        try:
            if info.pop(FAILED_KEY, False):
                self.session.rollback()
            else:
                self.session.commit()
        finally:
            self.session.close()

        return False

    def create(self, schema: CreateSchemaType) -> ModelType:
        """
        Generic create method - creates a new record from Pydantic schema.

        Args:
            schema: Pydantic schema instance with creation data

        Returns:
            Created model instance
        """
        instance = self.model_class(**schema.model_dump(exclude_unset=True))

        self.session.add(instance)
        self.session.flush()
        self.session.refresh(instance)

        return instance

    def update(self, id: uuid.UUID, schema: UpdateSchemaType) -> Optional[ModelType]:
        """
        Generic update method - updates a record from Pydantic schema.

        Only the fields set on the schema are changed (PATCH semantics).

        Args:
            id: Primary key of record to update
            schema: Pydantic schema instance with update data

        Returns:
            Updated model instance or None if not found
        """
        instance = self.get_by_id(id)

        if not instance:
            return None

        for field, value in schema.model_dump(exclude_unset=True).items():
            setattr(instance, field, value)

        self.session.flush()
        self.session.refresh(instance)

        return instance

    def delete(self, id: uuid.UUID) -> bool:
        """
        Generic soft delete method - sets deleted_at.

        Args:
            id: Primary key of record to delete

        Returns:
            True if deleted successfully, False if not found
        """
        instance = self.get_by_id(id)

        if not instance:
            return False

        instance.soft_delete()
        self.session.flush()

        return True

    def restore(self, id: uuid.UUID) -> Optional[ModelType]:
        """
        Generic restore method - clears deleted_at to restore a soft-deleted record.

        Args:
            id: Primary key of record to restore

        Returns:
            Restored model instance or None if not found
        """
        instance = self.get_by_id(id, include_deleted=True)

        if not instance:
            return None

        instance.restore()

        self.session.flush()
        self.session.refresh(instance)

        return instance

    def get_by_id(
        self, id: uuid.UUID, include_deleted: bool = False
    ) -> Optional[ModelType]:
        """
        Get a single record by primary key.

        Args:
            id: Primary key
            include_deleted: If True, include soft-deleted records

        Returns:
            Model instance or None if not found
        """
        query = self._query(include_deleted).where(self.model_class.id == id)

        return self.session.scalars(query).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> List[ModelType]:
        """
        Get all records with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_deleted: If True, include soft-deleted records

        Returns:
            List of model instances
        """
        query = self._query(include_deleted).offset(skip).limit(limit)

        return list(self.session.scalars(query))

    def _query(self, include_deleted: bool = False) -> Select:
        """
        Base SELECT for the model, filtering out soft-deleted records by default.

        Args:
            include_deleted: If True, include soft-deleted records

        Returns:
            SELECT statement to build on
        """
        query = select(self.model_class)

        if not include_deleted:
            query = query.where(self.model_class.deleted_at.is_(None))

        return query


class VersionedBaseRepository(
    BaseRepository[VersionedModelType, CreateSchemaType, UpdateSchemaType]
):
    """
    Base repository for versioned models - adds access to the change history.

    History rows are written automatically (app/db/repositories/versioning.py);
    this repository only reads them.
    """

    def get_history(self, id: uuid.UUID) -> List[Base]:
        """
        Get every recorded version of a record, oldest first.

        Includes the history of soft-deleted and hard-deleted records.

        Args:
            id: Primary key of the record

        Returns:
            List of history instances ordered by version
        """
        history_class = self.model_class.__history_class__
        query = (
            select(history_class)
            .where(history_class.id == id)
            .order_by(history_class.version, history_class.history_id)
        )

        return list(self.session.scalars(query))
