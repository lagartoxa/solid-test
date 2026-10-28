"""
Context manager protocol shared by every repository.
"""

from sqlalchemy.orm import Session

# Keys in session.info used to share the transaction between nested repositories.
NESTING_DEPTH_KEY = "repository_nesting_depth"
FAILED_KEY = "repository_failed"


class TransactionalRepository:
    """
    Repository used in a with statement that ends the transaction and closes the session.

    Usage:
        with MyRepository(session) as repo:
            ...

    To use more than one repository in the same transaction, nest the with
    statements. Only the outermost one commits (or rolls back) and closes the
    session:
        with UserRepository(session) as users:
            with CartRepository(session) as carts:
                ...
    """

    def __init__(self, session: Session):
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
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
