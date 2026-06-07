import uuid
from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel

from schemas.patient import PatientResponse


class CalendarSlot(BaseModel):
    id: uuid.UUID
    date: date
    start_time: time
    end_time: time
    is_booked: bool
    appointment_id: Optional[uuid.UUID] = None
    patient_name: Optional[str] = None


class DashboardResponse(BaseModel):
    total_patients: int
    booked_today: int
    available_today: int
    recent_patients: List[PatientResponse]
