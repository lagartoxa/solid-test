"""
Log repository - writes and reads the logs table.

Logs are append-only, so this repository has no update or delete.
"""

import uuid
from typing import List

from sqlalchemy import select

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
