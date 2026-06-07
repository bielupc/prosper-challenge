import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    session_id: uuid.UUID
    patient_id: Optional[uuid.UUID] = None
    patient_name: Optional[str] = None
    transcript: Optional[list] = None
    ended: bool = False


class ToolCallLogRequest(BaseModel):
    session_id: uuid.UUID
    patient_id: Optional[uuid.UUID] = None
    patient_name: Optional[str] = None
    tool_name: str
    arguments: Optional[dict] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    request_body: Optional[dict] = None
    response_status: Optional[int] = None
    response_body: Optional[Any] = None
    result: Optional[dict] = None
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0


class ToolCallLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tool_name: str
    arguments: Optional[dict] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    request_body: Optional[dict] = None
    response_status: Optional[int] = None
    response_body: Optional[Any] = None
    result: Optional[dict] = None
    success: bool
    error: Optional[str] = None
    duration_ms: int
    created_at: datetime


class CallSessionSummary(BaseModel):
    id: uuid.UUID
    patient_name: Optional[str] = None
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    tool_call_count: int
    failed_count: int


class CallSessionDetail(BaseModel):
    id: uuid.UUID
    patient_id: Optional[uuid.UUID] = None
    patient_name: Optional[str] = None
    status: str
    transcript: Optional[list] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    tool_calls: List[ToolCallLogResponse]
