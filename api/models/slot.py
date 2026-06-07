import uuid
from datetime import date, time

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


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
    is_booked: bool = Field(default=False)
