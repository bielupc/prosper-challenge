import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class CreatePatientRequest(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    phone: Optional[str] = None
    email: Optional[str] = None


class PatientResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date
    phone: Optional[str]
    email: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
