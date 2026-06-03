from datetime import date as date_type
from datetime import datetime, timezone
from typing import List

from core.database import get_session
from fastapi import APIRouter, Depends
from models import AvailabilitySlot
from schemas import SlotResponse
from sqlalchemy import and_, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


@router.get("/list_availability_slots", response_model=List[SlotResponse])
async def list_availability_slots(date: date_type, session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    result = await session.exec(
        select(AvailabilitySlot)
        .where(
            AvailabilitySlot.date == date,
            AvailabilitySlot.is_booked == False,
            or_(
                AvailabilitySlot.date > now.date(),
                and_(
                    AvailabilitySlot.date == now.date(), AvailabilitySlot.start_time >= now.time()
                ),
            ),
        )
        .order_by(AvailabilitySlot.start_time)
    )
    return result.all()
