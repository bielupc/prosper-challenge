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
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
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

_EHR_BASE = os.environ.get("EHR_API_BASE_URL", "http://localhost:8000")
_EHR_HEADERS = {"X-API-Key": os.environ.get("EHR_API_KEY", "")}


async def _ehr_post(path: str, body: dict) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{_EHR_BASE}{path}", json=body, headers=_EHR_HEADERS)
            return {"status": resp.status_code, **resp.json()}
    except Exception as e:
        return {"error": str(e)}


async def _ehr_get(path: str, params: dict) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_EHR_BASE}{path}", params=params, headers=_EHR_HEADERS)
            data = resp.json()
            # List responses need wrapping so status travels alongside
            if isinstance(data, list):
                return {"status": resp.status_code, "slots": data}
            return {"status": resp.status_code, **data}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def tool_find_patient(params: FunctionCallParams) -> None:
    result = await _ehr_get("/find_patient", params.arguments)
    await params.result_callback(result)


async def tool_create_patient(params: FunctionCallParams) -> None:
    result = await _ehr_post("/create_patient", params.arguments)
    await params.result_callback(result)


async def tool_list_availability_slots(params: FunctionCallParams) -> None:
    result = await _ehr_get("/list_availability_slots", params.arguments)
    await params.result_callback(result)


async def tool_create_appointment(params: FunctionCallParams) -> None:
    result = await _ehr_post("/create_appointment", params.arguments)
    await params.result_callback(result)


async def tool_cancel_appointment(params: FunctionCallParams) -> None:
    result = await _ehr_post("/cancel_appointment", params.arguments)
    await params.result_callback(result)


_TOOL_HANDLERS = {
    "find_patient": tool_find_patient,
    "create_patient": tool_create_patient,
    "list_availability_slots": tool_list_availability_slots,
    "create_appointment": tool_create_appointment,
    "cancel_appointment": tool_cancel_appointment,
}

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_TOOL_SCHEMAS = [
    FunctionSchema(
        name="find_patient",
        description="Look up an existing patient by full name and date of birth.",
        properties={
            "first_name": {"type": "string", "description": "Patient's first name"},
            "last_name": {"type": "string", "description": "Patient's last name"},
            "dob": {"type": "string", "description": "Date of birth, YYYY-MM-DD"},
        },
        required=["first_name", "last_name", "dob"],
    ),
    FunctionSchema(
        name="create_patient",
        description="Register a new patient in the EHR system.",
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
        description="Return available appointment slots for a given date.",
        properties={
            "date": {"type": "string", "description": "YYYY-MM-DD"},
        },
        required=["date"],
    ),
    FunctionSchema(
        name="create_appointment",
        description="Book a slot for a patient. Use IDs returned by find_patient/create_patient and list_availability_slots.",
        properties={
            "patient_id": {"type": "string", "description": "UUID from find_patient or create_patient"},
            "slot_id": {"type": "string", "description": "UUID from list_availability_slots"},
            "notes": {"type": "string"},
        },
        required=["patient_id", "slot_id"],
    ),
    FunctionSchema(
        name="cancel_appointment",
        description="Cancel an existing scheduled appointment.",
        properties={
            "appointment_id": {
                "type": "string",
                "description": "UUID of the appointment returned by create_appointment",
            },
        },
        required=["appointment_id"],
    ),
]

# ---------------------------------------------------------------------------
# Bot pipeline
# ---------------------------------------------------------------------------


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    elevenlabs_key = os.environ["ELEVENLABS_API_KEY"]
    stt = ElevenLabsRealtimeSTTService(api_key=elevenlabs_key)
    tts = ElevenLabsTTSService(api_key=elevenlabs_key, voice_id="SAz9YHcvj6GT2YYXdXww")

    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"])
    for name, handler in _TOOL_HANDLERS.items():
        llm.register_function(name, handler)

    today = date.today().strftime("%A, %B %d, %Y")
    messages = [
        {
            "role": "system",
            "content": f"""You are Prosper, a friendly AI scheduling assistant at Prosper Health clinic. Today is {today}.

Your job is to help patients book and manage appointments over the phone. Follow this flow:

1. Greet the caller and ask for their full name and date of birth.
2. Call find_patient. If found (status 200), confirm their name and continue. If not found (status 404), ask if they would like to register and call create_patient.
3. Ask which date they would like to come in (weekdays only, must be today or later).
4. Call list_availability_slots for that date. Read back available times naturally, for example "We have 9 AM, 9:30, and 10 AM available." If no slots are available, suggest trying another date.
5. When they choose a time, call create_appointment using their patient_id and the slot_id for that time. Confirm: "Perfect, you are booked for [date] at [time]."
6. To cancel, confirm which appointment, then call cancel_appointment with the appointment_id from when it was created.

Rules:
- Never read out raw IDs, UUIDs, or internal fields to the caller.
- Always confirm bookings and cancellations verbally before hanging up.
- Keep responses short and natural — this is a voice call.
- If a tool returns an error, apologize briefly and offer to try again.
- Only offer weekday slots; if the caller asks for a weekend, politely redirect.""",
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
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[RTVIObserver(rtvi)],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        messages.append(
            {
                "role": "system",
                "content": "Say hello and introduce yourself as Prosper, the Prosper Health scheduling assistant. Ask for the caller's full name and date of birth to get started.",
            }
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


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
