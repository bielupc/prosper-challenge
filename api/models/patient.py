import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Index, func, text
from sqlmodel import Field, SQLModel

from models.base import _tz_column, _utcnow


class Patient(SQLModel, table=True):
    __tablename__ = "patients"
    __table_args__ = (
        # Case-insensitive identity uniqueness
        Index(
            "uq_patient_identity",
            func.lower(text("first_name")),
            func.lower(text("last_name")),
            "date_of_birth",
            unique=True,
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    date_of_birth: date
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    source: Optional[str] = Field(default=None, max_length=50)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
