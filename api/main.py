from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

import models  # noqa: F401 — registers SQLModel metadata
from core.auth import api_key_middleware
from core.database import create_db
from core.seed import seed_slots
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import appointments, dashboard, events, patients, slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db()
    await seed_slots()
    yield


app = FastAPI(title="Prosper EHR", lifespan=lifespan)

app.middleware("http")(api_key_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(patients.router)
app.include_router(slots.router)
app.include_router(appointments.router)
app.include_router(dashboard.router)
app.include_router(events.router)
