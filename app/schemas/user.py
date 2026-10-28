"""
User schemas - input for the user repository.
"""

from typing import Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    name: str


class UserUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
