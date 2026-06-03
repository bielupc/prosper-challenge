from datetime import datetime, timezone

from core.database import get_session
from core.events import broadcast
from fastapi import APIRouter, Depends, HTTPException
from models import Appointment, AvailabilitySlot, Patient
from schemas import AppointmentResponse, CancelAppointmentRequest, CreateAppointmentRequest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


@router.post("/create_appointment", response_model=AppointmentResponse)
async def create_appointment(
    body: CreateAppointmentRequest, session: AsyncSession = Depends(get_session)
):
    patient = await session.get(Patient, body.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    slot = await session.get(AvailabilitySlot, body.slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    now = datetime.now(timezone.utc)
    if datetime.combine(slot.date, slot.start_time, tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=409, detail="Slot is in the past")

    appointment = Appointment(**body.model_dump())
    slot.is_booked = True
    session.add(appointment)
    session.add(slot)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Slot already booked")
    await session.refresh(appointment)
    await broadcast()
    return appointment


@router.post("/cancel_appointment", response_model=AppointmentResponse)
async def cancel_appointment(
    body: CancelAppointmentRequest, session: AsyncSession = Depends(get_session)
):
    appointment = await session.get(Appointment, body.appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.status == "cancelled":
        raise HTTPException(status_code=409, detail="Appointment already cancelled")

    slot = await session.get(AvailabilitySlot, appointment.slot_id)
    appointment.status = "cancelled"
    appointment.cancelled_at = datetime.now(timezone.utc)
    if slot:
        slot.is_booked = False
        session.add(slot)

    session.add(appointment)
    await session.commit()
    await session.refresh(appointment)
    await broadcast()
    return appointment
