import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CreateAppointmentRequest(BaseModel):
    patient_id: uuid.UUID
    slot_id: uuid.UUID
    notes: Optional[str] = None


class CancelAppointmentRequest(BaseModel):
    appointment_id: uuid.UUID


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    slot_id: uuid.UUID
    status: str
    notes: Optional[str]
    created_at: datetime
    cancelled_at: Optional[datetime]

    model_config = {"from_attributes": True}
