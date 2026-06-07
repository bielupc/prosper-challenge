import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, DateTime, Index
from sqlmodel import Field, SQLModel

from models.base import _tz_column, _utcnow


class CallSession(SQLModel, table=True):
    __tablename__ = "call_sessions"

    id: uuid.UUID = Field(primary_key=True)
    patient_id: Optional[uuid.UUID] = Field(default=None)
    patient_name: Optional[str] = Field(default=None, max_length=200)
    status: str = Field(default="active")
    transcript: Optional[list] = Field(default=None, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    ended_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class ToolCallLog(SQLModel, table=True):
    __tablename__ = "tool_call_logs"
    __table_args__ = (Index("ix_tool_call_logs_session", "session_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="call_sessions.id", ondelete="CASCADE")
    patient_id: Optional[uuid.UUID] = Field(default=None)
    patient_name: Optional[str] = Field(default=None, max_length=200)

    tool_name: str = Field(max_length=100)
    arguments: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    request_method: Optional[str] = Field(default=None, max_length=10)
    request_path: Optional[str] = Field(default=None, max_length=200)
    request_body: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    response_status: Optional[int] = Field(default=None)
    response_body: Optional[Any] = Field(default=None, sa_column=Column(JSON))

    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    success: bool = Field(default=True)
    error: Optional[str] = Field(default=None, max_length=500)
    duration_ms: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
