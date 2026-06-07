import uuid
from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, model_validator


class CreateAppointmentRequest(BaseModel):
    patient_id: uuid.UUID
    date: date
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def end_after_start(self) -> "CreateAppointmentRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class CancelAppointmentRequest(BaseModel):
    appointment_id: uuid.UUID
    patient_id: uuid.UUID


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    appointment_date: date
    start_time: time
    end_time: time
    status: str
    created_at: datetime
    cancelled_at: Optional[datetime]
