from datetime import date as date_type
from datetime import datetime
from typing import List, Optional

from core.database import get_session
from fastapi import APIRouter, Depends, HTTPException
from models import AvailabilitySlot
from schemas import SlotResponse
from sqlalchemy import and_, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


@router.get("/list_availability_slots", response_model=List[SlotResponse])
async def list_availability_slots(
    date: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    session: AsyncSession = Depends(get_session),
):
    if date is None and date_to is None:
        raise HTTPException(
            status_code=422,
            detail="Provide 'date' for a single day or 'date' + 'date_to' for a range",
        )
    if date_to is not None and date is None:
        raise HTTPException(status_code=422, detail="'date_to' requires 'date' as the range start")
    if date_to is not None and date_to < date:
        raise HTTPException(status_code=422, detail="'date_to' must be >= 'date'")

    now = datetime.now()
    end = date_to if date_to is not None else date

    result = await session.exec(
        select(AvailabilitySlot)
        .where(
            AvailabilitySlot.date >= date,
            AvailabilitySlot.date <= end,
            AvailabilitySlot.is_booked == False,
            or_(
                AvailabilitySlot.date > now.date(),
                and_(
                    AvailabilitySlot.date == now.date(), AvailabilitySlot.start_time >= now.time()
                ),
            ),
        )
        .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
    )
    return result.all()
