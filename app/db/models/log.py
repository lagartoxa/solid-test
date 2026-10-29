"""
Log model - every action done by the API, kept to track errors later.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Index, Integer, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.constants import LogAction
from app.db.models.base import Base, enum_check


class Log(Base):
    """
    One logged action: an API request, a database change or an external call.

    Append-only: a log is never updated or deleted, so it inherits Base
    instead of BaseModel (no updated_at, no soft delete).

    All rows of the same request share request_id.
    """

    __tablename__ = "logs"
    __table_args__ = (
        enum_check("action", LogAction, "logs_action_check"),
        Index("idx_logs_request_id", "request_id"),
        Index("idx_logs_created_at", "created_at"),
        Index("idx_logs_target_record_id", "target", "record_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    request_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    # API: "METHOD /path"; DB change: table name; external call: "service.operation".
    target: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    operation: Mapped[Optional[str]] = mapped_column(Text)
    # The User-Id header as received, so invalid values are logged too.
    user_id: Mapped[Optional[str]] = mapped_column(Text)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    request_payload: Mapped[Optional[Any]] = mapped_column(JSONB)
    response_payload: Mapped[Optional[Any]] = mapped_column(JSONB)
    error: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
