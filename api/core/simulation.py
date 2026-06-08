"""Simulation engine.

Drives an LLM "patient" against the real bot over a WebSocket, then evaluates the
resulting database state and the conversation against a scenario.
"""

import asyncio
import json
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone

import websockets
from loguru import logger
from models import Appointment, AppointmentSlot, AvailabilitySlot, Patient, ToolCallLog
from openai import AsyncOpenAI
from schemas.simulation import SimToolCall, SimTurn, SimulationResult
from sqlalchemy import func
from sqlmodel import select

from core.database import SessionLocal
from core.scenarios import SCENARIOS, Scenario, get_scenario

BOT_WS_URL = os.environ.get("BOT_WS_URL", "ws://bot:7861")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

_active_runners: dict[str, "SimulationRunner"] = {}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _split_name(full: str) -> tuple[str, str]:
    parts = full.split()
    return parts[0], parts[-1]


def _parse_time(hhmm: str) -> time:
    h, m = map(int, hhmm.split(":"))
    return time(h, m)


def _resolve_relative_date(relative: str) -> date:
    """Convert a scenario date ('tomorrow', 'next_monday', or ISO) to a date."""
    today = date.today()
    if relative == "tomorrow":
        return today + timedelta(days=1)
    if relative == "next_monday":
        days_ahead = 7 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)
    try:
        return date.fromisoformat(relative)
    except ValueError:
        return today


async def _find_patient(session, name: str, dob: str) -> Patient | None:
    """Look a patient up by name + DOB, case-insensitively."""
    first, last = _split_name(name)
    result = await session.exec(
        select(Patient).where(
            func.lower(Patient.first_name) == first.lower(),
            func.lower(Patient.last_name) == last.lower(),
            Patient.date_of_birth == date.fromisoformat(dob),
        )
    )
    return result.first()


async def _scheduled_appointments(session, patient_id) -> set[tuple]:
    """Return {(date, start, end)} for each active, scheduled appointment."""
    rows = (
        await session.exec(
            select(AppointmentSlot.appointment_id, AvailabilitySlot)
            .join(AvailabilitySlot, AvailabilitySlot.id == AppointmentSlot.slot_id)
            .join(Appointment, Appointment.id == AppointmentSlot.appointment_id)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status == "scheduled",
                AppointmentSlot.active == True,  # noqa: E712
            )
        )
    ).all()
    by_appt: dict = {}
    for appt_id, slot in rows:
        by_appt.setdefault(appt_id, []).append(slot)
    out = set()
    for slots in by_appt.values():
        slots.sort(key=lambda s: s.start_time)
        out.add((slots[0].date, slots[0].start_time, slots[-1].end_time))
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


class SimulationRunner:
    def __init__(self, scenario: Scenario):
        self.id = str(uuid.uuid4())
        self.scenario = scenario
        self.result = SimulationResult(
            id=self.id,
            scenario_id=scenario.id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self._llm = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._bot_session_id: str | None = None  # the bot's audit session UUID
        self._event_buffer: list[dict] = []  # replay for late-connecting SSE clients
        self._new_event = asyncio.Event()  # wakes event_stream when _emit appends
        self.task: asyncio.Task | None = None 

    # --- conversation -------------------------------------------------------

    async def run(self):
        """Connect to the bot, run the conversation, then evaluate."""
        try:
            await self._connect_and_run()
        except Exception as e:
            logger.exception("Simulation {} failed", self.id)
            self.result.status = "failed"
            self.result.reasoning = f"Simulation runner error: {e}"
        finally:
            self.result.completed_at = datetime.now(timezone.utc)
            await self._emit({"type": "complete", "result": self.result.model_dump()})
            _active_runners.pop(self.id, None)

    async def _connect_and_run(self):
        logger.info("Simulation {} starting scenario '{}'", self.id, self.scenario.id)
        async with websockets.connect(BOT_WS_URL) as ws:
            finished = False
            # Wait for the opening greeting (it may be preceded by the 'session'
            # system event). No greeting within 10s raises and fails the run.
            while not self.result.transcript:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
                if await self._handle_bot_message(msg) == "finished":
                    finished = True
                    break

            for _ in range(self.scenario.max_turns):
                if finished:
                    break
                patient_text = await self._generate_patient_response()
                self._record_turn("patient", patient_text)
                await self._emit({"type": "turn", "role": "patient", "text": patient_text})
                try:
                    await ws.send(json.dumps({"role": "user", "text": patient_text}))
                except websockets.exceptions.ConnectionClosed:
                    break  # the bot already ended the conversation

                got_agent = False
                while True:
                    msg = await self._recv(ws, 15.0)
                    if msg is None:
                        break
                    status = await self._handle_bot_message(msg)
                    if status == "finished":
                        finished = True
                        break
                    if status == "agent":
                        got_agent = True
                    elif status == "idle" and got_agent:
                        break

            if finished:
                logger.info("Simulation {} — bot signalled end of conversation", self.id)
            await self._evaluate()

    @staticmethod
    async def _recv(ws, timeout: float) -> dict | None:
        """Receive one JSON message, or None on timeout."""
        try:
            return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        except asyncio.TimeoutError:
            return None

    async def _handle_bot_message(self, msg: dict) -> str:
        """Process one bot message; return its status: 'agent', 'idle', 'finished',
        'session', or '' (nothing actionable)."""
        logger.debug("Simulation {} received: {}", self.id, msg)
        if msg.get("role") == "agent":
            self._record_turn("agent", msg["text"])
            await self._emit({"type": "turn", "role": "agent", "text": msg["text"]})
            return "agent"
        if msg.get("role") == "system":
            event = msg.get("event", "")
            if event == "session":
                self._bot_session_id = msg.get("session_id")
            return event
        return ""

    def _record_turn(self, role: str, text: str):
        self.result.transcript.append(
            SimTurn(role=role, text=text, timestamp=datetime.now(timezone.utc))
        )

    # --- LLM (patient + judge) --------------------------------------

    async def _chat(self, messages: list[dict], *, temperature: float, max_tokens: int) -> str:
        response = await self._llm.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    async def _generate_patient_response(self) -> str:
        """Ask an LLM to improvise the patient's next line."""
        system = (
            f"{self.scenario.persona}\n\n"
            f"Your goal: {self.scenario.goal}\n\n"
            "You are the PATIENT on a phone call with a clinic assistant. "
            "The assistant works for the clinic. You are calling them. "
            "Respond naturally in short sentences (1-2 sentences max). "
            "Do not use stage directions. Never speak for the assistant. "
            "Only say what YOU (the patient) would say. "
            "If the assistant asks a question, answer it directly. "
            "If they make an offer (e.g. 'would Monday work?'), accept or negotiate naturally."
        )
        # The agent's turns are the patient LLM's "user" turns, and vice versa.
        messages = [{"role": "system", "content": system}]
        for turn in self.result.transcript:
            role = "user" if turn.role == "agent" else "assistant"
            messages.append({"role": role, "content": turn.text})
        return await self._chat(messages, temperature=0.7, max_tokens=150)

    # --- evaluation ---------------------------------------------------------

    async def _evaluate(self):
        """Capture tool calls, run DB assertions + the LLM judge."""
        await self._load_tool_calls()
        db_ok, db_reason = await self._assert_db_state()
        judge_ok, judge_reason = await self._llm_judge()

        self.result.db_passed = db_ok
        self.result.judge_passed = judge_ok
        self.result.passed = db_ok and judge_ok
        self.result.reasoning = f"DB checks: {db_reason}\n\nJudge: {judge_reason}"
        self.result.status = "complete"

    async def _load_tool_calls(self):
        """Read the bot's tool calls from the shared audit store"""
        if not self._bot_session_id:
            logger.warning("Simulation {} — no bot session id; tool calls unavailable", self.id)
            return
        async with SessionLocal() as session:
            rows = (
                await session.exec(
                    select(ToolCallLog)
                    .where(ToolCallLog.session_id == uuid.UUID(self._bot_session_id))
                    .order_by(ToolCallLog.created_at)
                )
            ).all()
        self.result.tool_calls = [
            SimToolCall(
                name=r.tool_name,
                arguments=r.arguments or {},
                result=r.result,
                timestamp=r.created_at,
            )
            for r in rows
        ]

    async def _assert_db_state(self) -> tuple[bool, str]:
        """Assert the post-conversation DB state matches the scenario exactly."""
        expected = self.scenario.expected_db
        async with SessionLocal() as session:
            patient = await _find_patient(session, expected.patient_name, expected.patient_dob)
            if not patient:
                return False, f"Patient '{expected.patient_name}' (DOB {expected.patient_dob}) not found."

            if not (expected.appointment_date and expected.appointment_start and expected.appointment_end):
                return True, f"✅ Patient '{expected.patient_name}' exists."

            booked = await _scheduled_appointments(session, patient.id)
            target = (
                _resolve_relative_date(expected.appointment_date),
                _parse_time(expected.appointment_start),
                _parse_time(expected.appointment_end),
            )
            human = f"{target[0]} {target[1]}–{target[2]}"
            name = expected.patient_name

        if expected.appointment_scheduled:
            if target in booked:
                return True, f"✅ '{name}' has a scheduled appointment on {human}."
            return False, f"No scheduled appointment on {human} for '{name}'."
        if target in booked:
            return False, f"Expected the appointment on {human} to be cancelled, but it is still scheduled."
        return True, f"✅ '{name}' has no scheduled appointment on {human}."

    async def _llm_judge(self) -> tuple[bool, str]:
        """Use an LLM to evaluate conversation quality against the rubric."""
        transcript = "\n".join(
            f"{'Agent' if t.role == 'agent' else 'Patient'}: {t.text}"
            for t in self.result.transcript
        )
        rubric = "\n".join(f"- {item}" for item in self.scenario.rubric)
        prompt = f"""You are evaluating a voice-agent conversation for a healthcare clinic.
                Scenario: {self.scenario.name}
                Description: {self.scenario.description}

                Conversation transcript:
                {transcript}

                Evaluate the conversation against this rubric:
                {rubric}

                For each criterion, state whether it PASSED or FAILED and explain why.
                Then give an overall verdict (PASS or FAIL) and a one-sentence summary.

                Respond in this exact JSON format:
                {{
                "criteria": [
                    {{"criterion": "...", "verdict": "PASS|FAIL", "reason": "..."}}
                ],
                "overall_verdict": "PASS|FAIL",
                "summary": "..."
                }}
                """
        text = await self._chat([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=800)
        if text.startswith("```"): 
            text = text.split("```json")[-1].split("```")[0].strip()

        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError:
            return False, f"Judge returned unparsable response:\n{text}"

        passed = data.get("overall_verdict", "FAIL") == "PASS"
        criteria = "\n".join(
            f"{'✅' if c['verdict'] == 'PASS' else '❌'} {c['criterion']}: {c['reason']}"
            for c in data.get("criteria", [])
        )
        summary = data.get("summary", "No summary provided.")
        return passed, f"{criteria}\n\nSummary: {summary}"

    # --- SSE ----------------------------------------------------------------

    async def _emit(self, event: dict):
        self._event_buffer.append(event)
        self._new_event.set()

    async def event_stream(self):
        idx = 0
        while True:
            while idx < len(self._event_buffer):
                event = self._event_buffer[idx]
                idx += 1
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event.get("type") == "complete":
                    return
            self._new_event.clear()
            if idx >= len(self._event_buffer):
                await self._new_event.wait()


# --------------------------------------------------------------------------- #
# Module API
# --------------------------------------------------------------------------- #


def create_runner(scenario_id: str) -> SimulationRunner:
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise ValueError(f"Unknown scenario: {scenario_id}")
    runner = SimulationRunner(scenario)
    _active_runners[runner.id] = runner
    return runner


def get_runner(sim_id: str) -> SimulationRunner | None:
    return _active_runners.get(sim_id)


async def reset_simulation_data() -> dict:
    """Delete every scenario patient (currently just Alice Smith) and free their
    slots, for a clean slate. Deleting a patient cascades to their appointments."""
    identities = {
        (s.expected_db.patient_name, s.expected_db.patient_dob) for s in SCENARIOS.values()
    }
    deleted = 0
    async with SessionLocal() as session:
        for name, dob in identities:
            patient = await _find_patient(session, name, dob)
            if not patient:
                continue
            links = (
                await session.exec(
                    select(AppointmentSlot)
                    .join(Appointment, Appointment.id == AppointmentSlot.appointment_id)
                    .where(
                        Appointment.patient_id == patient.id,
                        AppointmentSlot.active == True,  # noqa: E712
                    )
                )
            ).all()
            for link in links:
                slot = await session.get(AvailabilitySlot, link.slot_id)
                if slot:
                    slot.is_booked = False
                    session.add(slot)
            await session.delete(patient)
            deleted += 1
        await session.commit()
    logger.info("Simulation reset — deleted {} patient(s)", deleted)
    return {"deleted_patients": deleted}
