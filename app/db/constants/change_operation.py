"""
Change operation values.
"""

from enum import Enum


class ChangeOperation(str, Enum):
    """
    The kind of change made to a record (used by history tables and logs).

    Soft delete and restore are updates of deleted_at, so they are recorded
    as UPDATE. DELETE is only used for hard deletes.
    """

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
