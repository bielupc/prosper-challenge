import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class CreatePatientRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[EmailStr] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return v


class PatientResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date
    phone: Optional[str]
    email: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
