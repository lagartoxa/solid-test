"""
Log schemas - API request and response bodies of the log endpoints.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.constants import LogAction

# ============================================================================
# API INPUT
# ============================================================================


class LogPath(BaseModel):
    log_id: uuid.UUID


class LogQuery(BaseModel):
    """Filters (all optional, combined with AND) and pagination of the log list."""

    request_id: Optional[uuid.UUID] = Field(default=None, description="All logs of one request")
    action: Optional[LogAction] = None
    user_id: Optional[str] = Field(default=None, description="User-Id header of the request")
    target: Optional[str] = Field(
        default=None, description='e.g. "POST /payments/webhook", "payments", "payment_provider.start_charge"'
    )
    record_id: Optional[uuid.UUID] = Field(default=None, description="Changes of one record")
    status_code: Optional[int] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    def filters(self) -> dict[str, Any]:
        """The filters that were sent, as column name -> value."""
        filters = self.model_dump(exclude={"limit", "offset"}, exclude_none=True)

        if "action" in filters:
            filters["action"] = filters["action"].value

        return filters


# ============================================================================
# API RESPONSES
# ============================================================================


class LogResponse(BaseModel):
    """A log entry, as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    request_id: Optional[uuid.UUID]
    action: LogAction
    target: str
    record_id: Optional[uuid.UUID]
    operation: Optional[str]
    user_id: Optional[str]
    status_code: Optional[int]
    request_payload: Any
    response_payload: Any
    error: Optional[str]
    duration_ms: Optional[int]


class LogListResponse(BaseModel):
    """A page of log entries, newest first."""

    items: list[LogResponse]
    total: int = Field(description="Number of entries matching the filters")
    limit: int
    offset: int
