"""
Log action values.
"""

from enum import Enum


class LogAction(str, Enum):
    """
    The kind of action recorded in the logs table.

    - api_request: a request received by the API and the response it sent.
    - db_change: a record inserted, updated or deleted.
    - external_call: a call to an external service (payment provider, ...).
    """

    API_REQUEST = "api_request"
    DB_CHANGE = "db_change"
    EXTERNAL_CALL = "external_call"
