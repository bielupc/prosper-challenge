#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
from datetime import date

import httpx
from dotenv import load_dotenv
from loguru import logger

print("🚀 Starting Pipecat bot...")
print("⏳ Loading models and imports (20 seconds, first run only)\n")

logger.info("Loading Local Smart Turn Analyzer V3...")
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3

logger.info("✅ Local Smart Turn Analyzer V3 loaded")
logger.info("Loading Silero VAD model...")
from pipecat.audio.vad.silero import SileroVADAnalyzer

logger.info("✅ Silero VAD model loaded")

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import ErrorFrame, LLMRunFrame, ManuallySwitchServiceFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.llm_switcher import LLMSwitcher
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.service_switcher import ServiceSwitcherStrategyManual
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies

logger.info("✅ All components loaded successfully!")

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# EHR API client
# ---------------------------------------------------------------------------

_EHR_BASE = os.environ.get("EHR_API_BASE_URL")
_EHR_HEADERS = {"X-API-Key": os.environ.get("EHR_API_KEY", "")}


def _friendly_error(resp: httpx.Response) -> dict:
    if 400 <= resp.status_code < 500:
        try:
            detail = resp.json().get("detail")
        except Exception:
            detail = None
        if isinstance(detail, str):
            return {"detail": detail}
        return {"detail": "The request was invalid. Please double-check the details and try again."}
    return {"detail": "The scheduling system is temporarily unavailable. Please try again."}


async def _ehr_post(client: httpx.AsyncClient, path: str, body: dict) -> tuple[bool, dict]:
    try:
        resp = await client.post(path, json=body)
    except httpx.RequestError:
        logger.exception("EHR POST %s failed", path)
        return False, {"detail": "Could not reach the scheduling system. Please try again."}
    if resp.is_success:
        return True, resp.json()
    logger.warning("EHR POST %s -> %s: %s", path, resp.status_code, resp.text)
    return False, _friendly_error(resp)


async def _ehr_get(client: httpx.AsyncClient, path: str, params: dict) -> tuple[bool, dict | list]:
    try:
        resp = await client.get(path, params=params)
    except httpx.RequestError:
        logger.exception("EHR GET %s failed", path)
        return False, {"detail": "Could not reach the scheduling system. Please try again."}
    if resp.is_success:
        return True, resp.json()
    logger.warning("EHR GET %s -> %s: %s", path, resp.status_code, resp.text)
    return False, _friendly_error(resp)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_TOOL_SCHEMAS = [
    FunctionSchema(
        name="find_patient",
        description="Look up a patient by full name and date of birth. Returns the patient's name on success, or found=false if not registered.",
        properties={
            "first_name": {"type": "string"},
            "last_name": {"type": "string"},
            "dob": {"type": "string", "description": "YYYY-MM-DD"},
        },
        required=["first_name", "last_name", "dob"],
    ),
    FunctionSchema(
        name="create_patient",
        description="Register a new patient in the EHR. Returns the patient's name on success.",
        properties={
            "first_name": {"type": "string"},
            "last_name": {"type": "string"},
            "date_of_birth": {"type": "string", "description": "YYYY-MM-DD"},
            "phone": {"type": "string"},
            "email": {"type": "string"},
        },
        required=["first_name", "last_name", "date_of_birth"],
    ),
    FunctionSchema(
        name="list_availability_slots",
        description="Return unbooked appointment slots. Pass date for a single day or date + date_to for a range. Returns slots with date, start_time, and end_time.",
        properties={
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "date_to": {"type": "string", "description": "YYYY-MM-DD, optional range end"},
        },
        required=["date"],
    ),
    FunctionSchema(
        name="list_appointments",
        description="Return all scheduled appointments for the current patient. Returns appointments with appointment_id, date, start_time, and end_time.",
        properties={},
        required=[],
    ),
    FunctionSchema(
        name="create_appointment",
        description=(
            "Book an appointment for the current patient over a time range. The range may "
            "span several consecutive slots and is booked as one appointment. Start and end "
            "must align with available 30-minute slot boundaries and be fully free. Returns "
            "appointment_id, date, start_time, and end_time on success."
        ),
        properties={
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "start_time": {"type": "string", "description": "HH:MM, aligned to a slot start"},
            "end_time": {"type": "string", "description": "HH:MM, aligned to a slot end"},
        },
        required=["date", "start_time", "end_time"],
    ),
    FunctionSchema(
        name="cancel_appointment",
        description="Cancel a scheduled appointment by appointment_id. Returns cancelled=true on success.",
        properties={
            "appointment_id": {
                "type": "string",
                "description": "UUID from list_appointments or create_appointment",
            },
        },
        required=["appointment_id"],
    ),
]

# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------


class _LLMFallbackObserver(BaseObserver):
    def __init__(self, primary, fallback):
        super().__init__()
        self._primary = primary
        self._fallback = fallback
        self.task: PipelineTask | None = None  # set after PipelineTask is created
        self._switched = False  # guard: only fall back once per call (avoids retry loops)

    async def on_push_frame(self, data: FramePushed):
        if self._switched or self.task is None:
            return
        frame = data.frame
        if isinstance(frame, ErrorFrame) and getattr(frame, "processor", None) is self._primary:
            self._switched = True
            logger.warning("Primary LLM failed ({}); switching to fallback", frame.error)
            await self.task.queue_frames(
                [ManuallySwitchServiceFrame(service=self._fallback), LLMRunFrame()]
            )


# ---------------------------------------------------------------------------
# Bot pipeline
# ---------------------------------------------------------------------------


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    client = httpx.AsyncClient(base_url=_EHR_BASE, headers=_EHR_HEADERS, timeout=10.0)
    # Per-session state, scoped to this connection, not shared across calls
    session: dict = {
        "auth": False,  # True once the caller is identified as a known patient
        "patient_id": None,
        "patient_name": None,
        "locked": False,  # True after any sensitive data access; blocks re-identification
        "valid_appt_ids": set(),  # appointment IDs belonging to this patient, safe to cancel
    }

    # ---Tool handlers ---
    async def tool_find_patient(params: FunctionCallParams) -> None:
        if session["locked"]:
            await params.result_callback(
                {
                    "found": True,
                    "name": session["patient_name"],
                    "note": "Identity locked — cannot re-identify after data has been accessed.",
                }
            )
            return
        ok, r = await _ehr_get(client, "/find_patient", params.arguments)
        if ok:
            session["auth"] = True
            session["patient_id"] = r["id"]
            session["patient_name"] = f"{r['first_name']} {r['last_name']}"
            await params.result_callback({"found": True, "name": session["patient_name"]})
        else:
            await params.result_callback({"found": False})

    async def tool_create_patient(params: FunctionCallParams) -> None:
        if session["locked"]:
            await params.result_callback(
                {
                    "registered": False,
                    "reason": "Identity locked — cannot re-identify after data has been accessed.",
                }
            )
            return
        ok, r = await _ehr_post(client, "/create_patient", params.arguments)
        if ok:
            session["auth"] = True
            session["patient_id"] = r["id"]
            session["patient_name"] = f"{r['first_name']} {r['last_name']}"
            await params.result_callback({"registered": True, "name": session["patient_name"]})
        else:
            await params.result_callback(
                {"registered": False, "reason": r.get("detail", "Registration failed")}
            )

    async def tool_list_availability_slots(params: FunctionCallParams) -> None:
        ok, r = await _ehr_get(client, "/list_availability_slots", params.arguments)
        if not ok:
            await params.result_callback(
                {"slots": [], "reason": r.get("detail", "Failed to fetch slots")}
            )
            return
        slots = [
            {
                "date": s["date"],
                "start_time": s["start_time"][:5],
                "end_time": s["end_time"][:5],
            }
            for s in (r if isinstance(r, list) else [])
        ]
        await params.result_callback({"slots": slots, "count": len(slots)})

    async def tool_list_appointments(params: FunctionCallParams) -> None:
        if not session["auth"]:
            await params.result_callback(
                {"appointments": [], "reason": "Patient not authenticated."}
            )
            return
        ok, r = await _ehr_get(client, "/list_appointments", {"patient_id": session["patient_id"]})
        if not ok:
            await params.result_callback(
                {"appointments": [], "reason": r.get("detail", "Failed to fetch appointments")}
            )
            return
        appointments = r if isinstance(r, list) else []
        for a in appointments:
            session["valid_appt_ids"].add(a["id"])
        session["locked"] = True
        result = [
            {
                "appointment_id": a["id"],
                "date": a["appointment_date"],
                "start_time": a["start_time"][:5],
                "end_time": a["end_time"][:5],
            }
            for a in appointments
        ]
        await params.result_callback({"appointments": result, "count": len(result)})

    async def tool_create_appointment(params: FunctionCallParams) -> None:
        if not session["auth"]:
            await params.result_callback({"booked": False, "reason": "Patient not authenticated."})
            return
        date_ = params.arguments.get("date")
        start_time = params.arguments.get("start_time")
        end_time = params.arguments.get("end_time")
        if not date_ or not start_time or not end_time:
            await params.result_callback(
                {"booked": False, "reason": "Missing date, start_time, or end_time."}
            )
            return
        ok, r = await _ehr_post(
            client,
            "/create_appointment",
            {
                "patient_id": session["patient_id"],
                "date": date_,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        if ok:
            session["valid_appt_ids"].add(r["id"])
            session["locked"] = True
            appt = {
                "appointment_id": r["id"],
                "date": r["appointment_date"],
                "start_time": r["start_time"][:5],
                "end_time": r["end_time"][:5],
            }
            await params.result_callback({"booked": True, **appt})
        else:
            await params.result_callback(
                {"booked": False, "reason": r.get("detail", "Booking failed")}
            )

    async def tool_cancel_appointment(params: FunctionCallParams) -> None:
        if not session["auth"]:
            await params.result_callback(
                {"cancelled": False, "reason": "Patient not authenticated."}
            )
            return
        appt_id = params.arguments.get("appointment_id")
        if appt_id not in session["valid_appt_ids"]:
            await params.result_callback(
                {
                    "cancelled": False,
                    "reason": "Appointment not found for this patient. Call list_appointments first.",
                }
            )
            return
        ok, r = await _ehr_post(
            client,
            "/cancel_appointment",
            {"appointment_id": appt_id, "patient_id": session["patient_id"]},
        )
        if ok:
            session["valid_appt_ids"].discard(appt_id)
            await params.result_callback({"cancelled": True, "appointment_id": appt_id})
        else:
            await params.result_callback(
                {"cancelled": False, "reason": r.get("detail", "Cancellation failed")}
            )

    # --- Register handlers ---
    elevenlabs_key = os.environ["ELEVENLABS_API_KEY"]
    stt = ElevenLabsRealtimeSTTService(api_key=elevenlabs_key)
    tts = ElevenLabsTTSService(api_key=elevenlabs_key, voice_id="SAz9YHcvj6GT2YYXdXww")

    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"])
    fallback_llm = AnthropicLLMService(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model=os.environ.get("FALLBACK_MODEL", "claude-haiku-4-5"),
    )

    llm_switcher = LLMSwitcher(
        llms=[llm, fallback_llm],
        strategy_type=ServiceSwitcherStrategyManual,
    )
    # Register tools on the switcher so the handler is registered on BOTH LLMs.
    llm_switcher.register_function("find_patient", tool_find_patient)
    llm_switcher.register_function("create_patient", tool_create_patient)
    llm_switcher.register_function("list_availability_slots", tool_list_availability_slots)
    llm_switcher.register_function("list_appointments", tool_list_appointments)
    llm_switcher.register_function("create_appointment", tool_create_appointment)
    llm_switcher.register_function("cancel_appointment", tool_cancel_appointment)

    today = date.today().strftime("%A, %B %d, %Y")
    messages = [
        {
            "role": "system",
            "content": f"""\
            You are Prosper, a scheduling assistant at Prosper Health clinic. Today is {today}.
            You speak naturally and concisely — this is a voice call, not a chat.

            ## PHASE 1 — Identify the caller

            Ask for the caller's full name and date of birth, then call find_patient.

            If found:
            - Confirm: "I have you down as [name]. How can I help you today?"
            - Ask whether they want to book or cancel an appointment.

            If not found:
            - Tell them they are not in the system and ask if they would like to register.
            - If yes: collect their phone and optionally email, then call create_patient with the previously collected full name and date of birth.
            Confirm: "You're all set, [name]. How can I help you today?"
            - If no: thank them and close the call politely.

            ## PHASE 2 — Understand intent

            After identification ask: "Would you like to book an appointment or cancel?"
            Handle whichever they ask for.

            ## PHASE 3A — Book an appointment

            1. Ask which date they would like to come in and roughly how long they need. Remind them the clinic is open Monday through Friday. Each opening is 30 minutes; a longer visit uses back-to-back openings.
            If they give a vague answer like "sometime next week", pick a specific weekday start and use date_to to search the full week.
            2. Call list_availability_slots. If count is 0, say there are no slots that day and suggest the next available weekday.
            3. Read back the times naturally: "We have openings at 9, 9:30, and 10 AM — which works for you?"
            4. Pick a start_time and an end_time that cover the requested length using only consecutive free openings (for a 1-hour visit at 9, that's start 09:00 to end 10:00). Call create_appointment with date, start_time, and end_time.
            5. Confirm: "Done — you're booked for [day], [date] from [start_time] to [end_time]."
            6. Ask: "Is there anything else I can help you with?"

            ## PHASE 3B — Cancel an appointment

            1. Call list_appointments to retrieve all scheduled appointments for the patient.
            2. If count is 0, tell them they have no upcoming appointments.
            3. If there is one, confirm it by date and time before cancelling.
            4. If there are multiple, read them out by date and time and ask which one to cancel.
            5. Call cancel_appointment with the chosen appointment_id.
            6. Confirm: "Done — your [day] [date] at [time] appointment has been cancelled."

            Never ask the caller for an appointment ID — always identify by date and time.

            ## Rules

            - Never say UUIDs, IDs, or field names aloud — they are internal only.
            - Keep every response short. One or two sentences is ideal.
            - Do not use filler phrases like "Of course!", "Certainly!", or "Absolutely!".
            - If a tool returns an error, apologize briefly and offer to try again or suggest calling the front desk.
            - If the caller gives a weekend date, redirect: "We're only open Monday through Friday — would [next Monday] work?"
            """,
        },
    ]

    context = LLMContext(messages, tools=ToolsSchema(standard_tools=_TOOL_SCHEMAS))
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]
            ),
        ),
    )

    rtvi = RTVIProcessor()

    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,
            stt,
            user_aggregator,
            llm_switcher,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    fallback_obs = _LLMFallbackObserver(primary=llm, fallback=fallback_llm)
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[RTVIObserver(rtvi), fallback_obs],
    )
    fallback_obs.task = task  # observer needs the task to queue the switch + retry

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        messages.append(
            {
                "role": "system",
                "content": "The call has connected. Greet the caller and begin Phase 1.",
            }
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    try:
        await runner.run(task)
    finally:
        await client.aclose()


async def bot(runner_args: RunnerArguments):
    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    }

    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
