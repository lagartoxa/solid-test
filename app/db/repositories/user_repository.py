"""
User repository for user-related database operations.
"""

from typing import Optional

from app.db.models.user import User
from app.db.repositories.base import BaseRepository
from app.schemas.user import UserCreate, UserUpdate


class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    """Repository for User model."""

    model_class = User

    def get_by_email(self, email: str) -> Optional[User]:
        """
        Get active user by email address.

        Args:
            email: User email

        Returns:
            User instance or None if not found
        """
        return self.session.scalars(self._query().where(User.email == email)).first()
