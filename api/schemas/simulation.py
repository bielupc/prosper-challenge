from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ScenarioSummary(BaseModel):
    id: str
    name: str
    description: str


class ExpectedDB(BaseModel):
    patient_name: str
    patient_dob: str
    appointment_date: Optional[str] = None
    appointment_start: Optional[str] = None
    appointment_end: Optional[str] = None
    # True  → a scheduled appointment matching the date/start/end must exist.
    # False → the patient must have NO scheduled appointment
    appointment_scheduled: bool = True


class Scenario(BaseModel):
    id: str
    name: str
    description: str
    persona: str
    goal: str
    expected_db: ExpectedDB
    rubric: list[str] = Field(default_factory=list)
    max_turns: int = 20


class SimulationRequest(BaseModel):
    scenario_id: str


class SimTurn(BaseModel):
    role: str  # "patient" | "agent"
    text: str
    timestamp: datetime


class SimToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    result: Any
    timestamp: datetime


class SimulationResult(BaseModel):
    id: str
    scenario_id: str
    status: str  # "running" | "complete" | "failed"
    transcript: list[SimTurn] = Field(default_factory=list)
    tool_calls: list[SimToolCall] = Field(default_factory=list)
    db_passed: bool = False
    judge_passed: bool = False
    passed: bool = False
    reasoning: str = ""
    started_at: datetime
    completed_at: Optional[datetime] = None
