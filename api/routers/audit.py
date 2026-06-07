import uuid
from datetime import datetime, timezone
from typing import List

from core.database import get_session
from core.events import broadcast
from fastapi import APIRouter, Depends, HTTPException
from models import CallSession, ToolCallLog
from schemas import (
    CallSessionDetail,
    CallSessionSummary,
    CreateSessionRequest,
    ToolCallLogRequest,
    ToolCallLogResponse,
)
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


@router.post("/audit/session", status_code=200)
async def upsert_session(
    body: CreateSessionRequest, session: AsyncSession = Depends(get_session)
):
    row = await session.get(CallSession, body.session_id)
    if row is None:
        row = CallSession(id=body.session_id)
        session.add(row)

    if body.patient_id is not None:
        row.patient_id = body.patient_id
    if body.patient_name is not None:
        row.patient_name = body.patient_name
    if body.transcript is not None:
        row.transcript = body.transcript
    if body.ended:
        row.status = "ended"
        row.ended_at = datetime.now(timezone.utc)

    await session.commit()
    await broadcast()
    return {"ok": True}


@router.post("/audit/tool_call", status_code=201)
async def log_tool_call(
    body: ToolCallLogRequest, session: AsyncSession = Depends(get_session)
):
    log = ToolCallLog(**body.model_dump())
    session.add(log)
    await session.commit()
    await broadcast()
    return {"ok": True}


@router.get("/audit/sessions", response_model=List[CallSessionSummary])
async def list_sessions(session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                sa_select(
                    CallSession.id,
                    CallSession.patient_name,
                    CallSession.status,
                    CallSession.started_at,
                    CallSession.ended_at,
                    func.count(ToolCallLog.id).label("tool_call_count"),
                    func.count(ToolCallLog.id)
                    .filter(ToolCallLog.success == False)  # noqa: E712
                    .label("failed_count"),
                )
                .outerjoin(ToolCallLog, ToolCallLog.session_id == CallSession.id)
                .group_by(CallSession.id)
                .order_by(CallSession.started_at.desc())
                .limit(100)
            )
        )
        .mappings()
        .all()
    )
    return [CallSessionSummary(**row) for row in rows]


@router.get("/audit/sessions/{session_id}", response_model=CallSessionDetail)
async def get_session_detail(
    session_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    row = await session.get(CallSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    calls = (
        (
            await session.exec(
                select(ToolCallLog)
                .where(ToolCallLog.session_id == session_id)
                .order_by(ToolCallLog.created_at)
            )
        )
        .all()
    )

    return CallSessionDetail(
        id=row.id,
        patient_id=row.patient_id,
        patient_name=row.patient_name,
        status=row.status,
        transcript=row.transcript,
        started_at=row.started_at,
        ended_at=row.ended_at,
        tool_calls=[ToolCallLogResponse.model_validate(c) for c in calls],
    )
