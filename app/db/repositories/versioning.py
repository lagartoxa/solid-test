"""
History writer for versioned models.

A single after_flush listener on every Session writes one history row for each
versioned record inserted, updated or deleted in the flush, in the same
transaction as the change.

Only changes made through ORM instances are recorded. Bulk statements
(session.execute(update(...))) skip ORM events and must not be used on
versioned tables.
"""

from sqlalchemy import event, insert
from sqlalchemy.orm import Session

from app.db.constants import HistoryOperation
from app.db.models.base import VersionedBaseModel


@event.listens_for(Session, "after_flush")
def record_history(session: Session, flush_context) -> None:
    """
    Write the history rows of the versioned records changed in this flush.

    after_flush runs once the changes reached the database, so generated values
    (id, version, server defaults) are already on the instances, while
    session.new / dirty / deleted still list what was flushed.
    """
    changes = [
        *((instance, HistoryOperation.INSERT) for instance in session.new),
        *(
            (instance, HistoryOperation.UPDATE)
            for instance in session.dirty
            if session.is_modified(instance, include_collections=False)
        ),
        *((instance, HistoryOperation.DELETE) for instance in session.deleted),
    ]

    for instance, operation in changes:
        if isinstance(instance, VersionedBaseModel):
            _insert_snapshot(session, instance, operation)


def _insert_snapshot(
    session: Session, instance: VersionedBaseModel, operation: HistoryOperation
) -> None:
    """
    Insert a copy of the instance's current values into its history table.

    Args:
        session: Session being flushed
        instance: Versioned record that changed
        operation: Kind of change
    """
    history_table = instance.__history_class__.__table__
    snapshot = {
        column.name: getattr(instance, column.name)
        for column in history_table.columns
        if column.name in instance.__table__.columns
    }

    # A deleted row's version is not incremented (the row is gone), but the
    # delete is a new event in its history, so it gets the next version.
    if operation is HistoryOperation.DELETE:
        snapshot["version"] += 1

    session.connection().execute(
        insert(history_table).values(**snapshot, operation=operation.value)
    )
