import uuid

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class AppointmentSlot(SQLModel, table=True):
    __tablename__ = "appointment_slots"
    __table_args__ = (
        # Double-booking guard: a slot can belong to at most one active appointment.
        Index(
            "uq_appointment_slot_active",
            "slot_id",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    appointment_id: uuid.UUID = Field(
        foreign_key="appointments.id", ondelete="CASCADE", primary_key=True
    )
    slot_id: uuid.UUID = Field(foreign_key="availability_slots.id", primary_key=True)
    # False once the parent appointment is cancelled
    active: bool = Field(default=True)
