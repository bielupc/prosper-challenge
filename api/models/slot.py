import uuid
from datetime import date, datetime, time

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from models.base import _tz_column, _utcnow


class AvailabilitySlot(SQLModel, table=True):
    __tablename__ = "availability_slots"
    __table_args__ = (
        UniqueConstraint("date", "start_time", name="uq_slots_date_start"),
        Index("ix_slots_date_booked", "date", "is_booked"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    date: date
    start_time: time
    end_time: time
    # Denormalized flag for O(1) availability reads — flipped atomically with appointments
    is_booked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
