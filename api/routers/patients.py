from datetime import date

from core.database import get_session
from core.events import broadcast
from fastapi import APIRouter, Depends, HTTPException
from models import Patient
from schemas import CreatePatientRequest, PatientResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()


@router.post("/create_patient", response_model=PatientResponse, status_code=201)
async def create_patient(body: CreatePatientRequest, session: AsyncSession = Depends(get_session)):
    patient = Patient(**body.model_dump())
    session.add(patient)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Patient already registered") from None
    await session.refresh(patient)
    await broadcast()
    return patient


@router.get("/find_patient", response_model=PatientResponse)
async def find_patient(
    first_name: str,
    last_name: str,
    dob: date,
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(
        select(Patient).where(
            func.lower(Patient.first_name) == first_name.strip().lower(),
            func.lower(Patient.last_name) == last_name.strip().lower(),
            Patient.date_of_birth == dob,
        )
    )
    patient = result.first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient
