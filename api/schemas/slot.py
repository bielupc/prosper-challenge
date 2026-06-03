import uuid
from datetime import date, time

from pydantic import BaseModel


class SlotResponse(BaseModel):
    id: uuid.UUID
    date: date
    start_time: time
    end_time: time
    is_booked: bool

    model_config = {"from_attributes": True}
