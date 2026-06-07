import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime
from sqlmodel import Field, SQLModel

from models.base import _tz_column, _utcnow


class Appointment(SQLModel, table=True):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled', 'cancelled')", name="ck_appointment_status"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    patient_id: uuid.UUID = Field(foreign_key="patients.id", ondelete="CASCADE")
    status: str = Field(default="scheduled")
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    cancelled_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
