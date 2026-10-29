"""
Log repository - writes and reads the logs table.

Logs are append-only, so this repository has no update or delete.
"""

import uuid
from typing import Any, List, Optional

from sqlalchemy import func, select

from app.db.models.log import Log
from app.db.repositories.transactional import TransactionalRepository


class LogRepository(TransactionalRepository):
    """Repository for Log model."""

    def add(self, entry: Log) -> Log:
        """
        Save a log entry.

        Args:
            entry: Log entry built by the action logger

        Returns:
            Saved log entry
        """
        self.session.add(entry)
        self.session.flush()

        return entry

    def get_by_request_id(self, request_id: uuid.UUID) -> List[Log]:
        """
        Get every log of a request, oldest first.

        Args:
            request_id: Id of the request (X-Request-ID response header)

        Returns:
            List of log entries
        """
        query = (
            select(Log)
            .where(Log.request_id == request_id)
            .order_by(Log.created_at, Log.id)
        )

        return list(self.session.scalars(query))

    def get_by_id(self, id: uuid.UUID) -> Optional[Log]:
        """
        Get a log entry by id.

        Args:
            id: Log id (e.g. the log_id of an unexpected error response)

        Returns:
            Log entry or None if not found
        """
        return self.session.get(Log, id)

    def search(self, filters: dict[str, Any], limit: int, offset: int) -> tuple[List[Log], int]:
        """
        Get log entries matching every filter, newest first.

        Args:
            filters: Column name -> value; each one must match exactly
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            The page of entries and the total number of matching entries
        """
        conditions = [getattr(Log, column) == value for column, value in filters.items()]

        page = (
            select(Log)
            .where(*conditions)
            .order_by(Log.created_at.desc(), Log.id)
            .limit(limit)
            .offset(offset)
        )
        total = select(func.count()).select_from(Log).where(*conditions)

        return list(self.session.scalars(page)), self.session.scalar(total)
