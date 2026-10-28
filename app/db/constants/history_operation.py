"""
History operation values.
"""

from enum import Enum


class HistoryOperation(str, Enum):
    """
    The kind of change recorded in a history table.

    Soft delete and restore are updates of deleted_at, so they are recorded
    as UPDATE. DELETE is only used for hard deletes.
    """

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
