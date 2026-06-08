import uuid
from datetime import datetime, timezone
from typing import List

from core.database import get_session
from core.events import broadcast
from fastapi import APIRouter, Depends, HTTPException
from models import Appointment, AppointmentSlot, AvailabilitySlot, Patient
from schemas import AppointmentResponse, CancelAppointmentRequest, CreateAppointmentRequest
from sqlalchemy import select as sa_select
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


def _appointment_response(
    appointment: Appointment, slots: list[AvailabilitySlot]
) -> AppointmentResponse:
    ordered = sorted(slots, key=lambda s: s.start_time)
    return AppointmentResponse(
        id=appointment.id,
        patient_id=appointment.patient_id,
        appointment_date=ordered[0].date,
        start_time=ordered[0].start_time,
        end_time=ordered[-1].end_time,
        status=appointment.status,
        created_at=appointment.created_at,
        cancelled_at=appointment.cancelled_at,
    )


@router.post("/create_appointment", response_model=AppointmentResponse, status_code=201)
async def create_appointment(
    body: CreateAppointmentRequest, session: AsyncSession = Depends(get_session)
):
    patient = await session.get(Patient, body.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    result = await session.exec(
        select(AvailabilitySlot)
        .where(
            AvailabilitySlot.date == body.date,
            AvailabilitySlot.start_time >= body.start_time,
            AvailabilitySlot.start_time < body.end_time,
        )
        .order_by(AvailabilitySlot.start_time)
    )
    slots = result.all()

    # The requested range must exactly tile contiguous slots
    if (
        not slots
        or slots[0].start_time != body.start_time
        or slots[-1].end_time != body.end_time
        or any(slots[i].end_time != slots[i + 1].start_time for i in range(len(slots) - 1))
    ):
        raise HTTPException(
            status_code=422,
            detail="Requested range does not align with available 30-minute slots",
        )

    if datetime.combine(slots[0].date, slots[0].start_time) < datetime.now():
        raise HTTPException(status_code=409, detail="Slot is in the past")

    if any(s.is_booked for s in slots):
        raise HTTPException(status_code=409, detail="Slot already booked")

    appointment = Appointment(patient_id=body.patient_id)
    session.add(appointment)
    for s in slots:
        s.is_booked = True
        session.add(s)
        session.add(AppointmentSlot(appointment_id=appointment.id, slot_id=s.id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Slot already booked") from None
    await session.refresh(appointment)
    await broadcast()
    return _appointment_response(appointment, slots)


@router.post("/cancel_appointment", response_model=AppointmentResponse)
async def cancel_appointment(
    body: CancelAppointmentRequest, session: AsyncSession = Depends(get_session)
):
    appointment = await session.get(Appointment, body.appointment_id)
    if not appointment or appointment.patient_id != body.patient_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.status == "cancelled":
        raise HTTPException(status_code=409, detail="Appointment already cancelled")

    rows = (
        await session.execute(
            sa_select(AppointmentSlot, AvailabilitySlot)
            .join(AvailabilitySlot, AvailabilitySlot.id == AppointmentSlot.slot_id)
            .where(
                AppointmentSlot.appointment_id == appointment.id,
                AppointmentSlot.active == True,
            )
            .order_by(AvailabilitySlot.start_time)
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=409, detail="Appointment already cancelled")

    appointment.status = "cancelled"
    appointment.cancelled_at = datetime.now(timezone.utc)
    session.add(appointment)
    slots = []
    for link, slot in rows:
        link.active = False
        slot.is_booked = False
        session.add(link)
        session.add(slot)
        slots.append(slot)

    await session.commit()
    await session.refresh(appointment)
    await broadcast()
    return _appointment_response(appointment, slots)


@router.get("/list_appointments", response_model=List[AppointmentResponse])
async def list_appointments(patient_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            sa_select(Appointment, AvailabilitySlot)
            .join(AppointmentSlot, AppointmentSlot.appointment_id == Appointment.id)
            .join(AvailabilitySlot, AvailabilitySlot.id == AppointmentSlot.slot_id)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status == "scheduled",
                AppointmentSlot.active == True,
            )
            .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
        )
    ).all()

    grouped: dict[uuid.UUID, tuple[Appointment, list[AvailabilitySlot]]] = {}
    order: list[uuid.UUID] = []
    for appt, slot in rows:
        if appt.id not in grouped:
            grouped[appt.id] = (appt, [])
            order.append(appt.id)
        grouped[appt.id][1].append(slot)

    return [_appointment_response(*grouped[appt_id]) for appt_id in order]
