import os
from datetime import date, datetime, time, timedelta

from models import AvailabilitySlot
from sqlmodel import select

from core.database import SessionLocal

_CLINIC_START = int(os.environ.get("CLINIC_START_HOUR", "9"))
_CLINIC_END = int(os.environ.get("CLINIC_END_HOUR", "17"))
_SLOT_MINUTES = int(os.environ.get("SLOT_MINUTES", "30"))
_DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "60"))


async def seed_slots():
    async with SessionLocal() as session:
        existing = await session.exec(select(AvailabilitySlot).limit(1))
        if existing.first():
            return

        today = date.today()
        slots = []

        for offset in range(_DAYS_AHEAD):
            d = today + timedelta(days=offset)
            if d.weekday() >= 5:
                continue

            current = datetime.combine(d, time(_CLINIC_START, 0))
            end = datetime.combine(d, time(_CLINIC_END, 0))

            while current < end:
                slot_end = current + timedelta(minutes=_SLOT_MINUTES)
                slots.append(
                    AvailabilitySlot(
                        date=d,
                        start_time=current.time(),
                        end_time=slot_end.time(),
                    )
                )
                current = slot_end

        session.add_all(slots)
        await session.commit()
