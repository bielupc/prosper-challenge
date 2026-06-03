import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, Index, text
from sqlmodel import Field, SQLModel

from models.base import _tz_column, _utcnow


class Appointment(SQLModel, table=True):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled', 'cancelled')", name="ck_appointment_status"),
        # Prevents double-booking at the DB level
        Index(
            "ix_appointments_slot_scheduled",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'scheduled'"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    patient_id: uuid.UUID = Field(foreign_key="patients.id", ondelete="CASCADE")
    slot_id: uuid.UUID = Field(foreign_key="availability_slots.id")
    status: str = Field(default="scheduled")
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    cancelled_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
