"""
Log service - reads the action log, so the support team can trace errors.
"""

import uuid

from sqlalchemy.orm import Session

from app.db.models import Log
from app.db.repositories import LogRepository
from app.db.session import get_session
from app.schemas.log import LogQuery
from app.services.errors import ErrorCode, NotFoundError


class LogService:
    """Read-only access to the logs."""

    def __init__(self, session: Session):
        self.session = session

    def get_log(self, log_id: uuid.UUID) -> Log:
        """
        Get one log entry.

        Raises:
            NotFoundError: the log doesn't exist
        """
        with LogRepository(self.session) as logs:
            log = logs.get_by_id(log_id)

            if log is None:
                raise NotFoundError(ErrorCode.LOG_NOT_FOUND, "Log not found.")

            return log

    def search_logs(self, query: LogQuery) -> tuple[list[Log], int]:
        """Get a page of logs matching the query's filters, and the total."""
        with LogRepository(self.session) as logs:
            return logs.search(query.filters(), query.limit, query.offset)


def build_log_service() -> LogService:
    """Log service for the current request."""
    return LogService(get_session())
