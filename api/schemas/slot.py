import uuid
from datetime import date, time

from pydantic import BaseModel, computed_field


class SlotResponse(BaseModel):
    id: uuid.UUID
    date: date
    start_time: time
    end_time: time

    @computed_field
    @property
    def duration_minutes(self) -> int:
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return end - start

    model_config = {"from_attributes": True}
