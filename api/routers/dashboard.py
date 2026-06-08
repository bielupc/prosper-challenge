from datetime import date, timedelta
from typing import List

from core.database import get_session
from fastapi import APIRouter, Depends
from models import Appointment, AppointmentSlot, AvailabilitySlot, Patient
from schemas import CalendarSlot, DashboardResponse, PatientResponse
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(session: AsyncSession = Depends(get_session)):
    today = date.today()

    total_patients = (await session.execute(sa_select(func.count(Patient.id)))).scalar_one()

    booked_today = (
        await session.execute(
            sa_select(func.count(func.distinct(Appointment.id)))
            .join(AppointmentSlot, AppointmentSlot.appointment_id == Appointment.id)
            .join(AvailabilitySlot, AvailabilitySlot.id == AppointmentSlot.slot_id)
            .where(
                AvailabilitySlot.date == today,
                Appointment.status == "scheduled",
                AppointmentSlot.active == True,
            )
        )
    ).scalar_one()

    available_today = (
        await session.execute(
            sa_select(func.count(AvailabilitySlot.id)).where(
                AvailabilitySlot.date == today, AvailabilitySlot.is_booked == False
            )
        )
    ).scalar_one()

    recent_patients_rows = (
        (await session.execute(sa_select(Patient).order_by(Patient.created_at.desc()).limit(20)))
        .scalars()
        .all()
    )

    return DashboardResponse(
        total_patients=total_patients,
        booked_today=booked_today,
        available_today=available_today,
        recent_patients=[PatientResponse.model_validate(p) for p in recent_patients_rows],
    )


@router.get("/calendar", response_model=List[CalendarSlot])
async def calendar(start: date, session: AsyncSession = Depends(get_session)):
    end = start + timedelta(days=6)

    rows = (
        (
            await session.execute(
                sa_select(
                    AvailabilitySlot.id,
                    AvailabilitySlot.date,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                    AvailabilitySlot.is_booked,
                    Appointment.id.label("appointment_id"),
                    (Patient.first_name + " " + Patient.last_name).label("patient_name"),
                )
                .outerjoin(
                    AppointmentSlot,
                    (AppointmentSlot.slot_id == AvailabilitySlot.id)
                    & (AppointmentSlot.active == True),
                )
                .outerjoin(
                    Appointment,
                    (Appointment.id == AppointmentSlot.appointment_id)
                    & (Appointment.status == "scheduled"),
                )
                .outerjoin(Patient, Patient.id == Appointment.patient_id)
                .where(AvailabilitySlot.date >= start, AvailabilitySlot.date <= end)
                .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
            )
        )
        .mappings()
        .all()
    )

    return [CalendarSlot(**row) for row in rows]
