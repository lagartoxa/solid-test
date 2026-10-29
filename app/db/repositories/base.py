"""
Base repository with generic CRUD operations and context manager protocol.
"""

import uuid
from typing import Any, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.constants import ChangeOperation
from app.db.models.base import Base, BaseModel, VersionedBaseModel
from app.db.repositories.transactional import TransactionalRepository
from app.log.action_logger import action_logger

ModelType = TypeVar("ModelType", bound=BaseModel)
VersionedModelType = TypeVar("VersionedModelType", bound=VersionedBaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=PydanticBaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=PydanticBaseModel)


class BaseRepository(
    TransactionalRepository, Generic[ModelType, CreateSchemaType, UpdateSchemaType]
):
    """
    Base repository implementing generic CRUD operations.

    All repositories must inherit from this class and set the model_class
    attribute. Used in a with statement (see TransactionalRepository):
        with MyRepository(session) as repo:
            item = repo.create(schema)

    Every method that changes data logs the change with _log_change, in the
    same transaction as the change.
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

        super().__init__(session)

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

        self._log_change(instance, ChangeOperation.INSERT, after=instance.column_values())

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

        data = schema.model_dump(exclude_unset=True)
        before = {field: getattr(instance, field) for field in data}

        for field, value in data.items():
            setattr(instance, field, value)

        self.session.flush()
        self.session.refresh(instance)

        changed = [field for field in data if getattr(instance, field) != before[field]]
        if changed:
            self._log_change(
                instance,
                ChangeOperation.UPDATE,
                before={field: before[field] for field in changed},
                after={field: getattr(instance, field) for field in changed},
            )

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

        self._log_change(
            instance,
            ChangeOperation.UPDATE,
            before={"deleted_at": None},
            after={"deleted_at": instance.deleted_at},
        )

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

        deleted_at = instance.deleted_at
        instance.restore()

        self.session.flush()
        self.session.refresh(instance)

        self._log_change(
            instance,
            ChangeOperation.UPDATE,
            before={"deleted_at": deleted_at},
            after={"deleted_at": None},
        )

        return instance

    def get_by_id(
        self, id: uuid.UUID, include_deleted: bool = False, for_update: bool = False
    ) -> Optional[ModelType]:
        """
        Get a single record by primary key.

        Args:
            id: Primary key
            include_deleted: If True, include soft-deleted records
            for_update: If True, lock the row until the transaction ends
                (SELECT ... FOR UPDATE), so concurrent requests wait

        Returns:
            Model instance or None if not found
        """
        query = self._query(include_deleted).where(self.model_class.id == id)

        if for_update:
            query = query.with_for_update()

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

    def _log_change(
        self,
        instance: ModelType,
        operation: ChangeOperation,
        before: Optional[dict[str, Any]] = None,
        after: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Log a change of a record, in the same transaction as the change.

        Every repository method that changes data must call it, so a rolled
        back change leaves no log.

        Args:
            instance: Changed record
            operation: Kind of change
            before: Values before the change (changed fields only)
            after: Values after the change (changed fields only)
        """
        self.session.add(
            action_logger.db_change_entry(
                instance.__tablename__, instance.id, operation, before, after
            )
        )


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
