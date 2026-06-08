#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

print("🚀 Starting Pipecat bot...")
print("⏳ Loading models and imports (20 seconds, first run only)\n")

from loguru import logger

logger.info("Loading Local Smart Turn Analyzer V3...")
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3

logger.info("✅ Local Smart Turn Analyzer V3 loaded")
logger.info("Loading Silero VAD model...")
from pipecat.audio.vad.silero import SileroVADAnalyzer

logger.info("✅ Silero VAD model loaded")

from audit import AuditLogger
from ehr import make_client
from nodes import build_system_prompt, create_collect_identity_node
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
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat_flows import FlowManager

logger.info("✅ All components loaded successfully!")

# ---------------------------------------------------------------------------
# LLM fallback observer
# ---------------------------------------------------------------------------


class _LLMFallbackObserver(BaseObserver):
    def __init__(self, primary, fallback):
        super().__init__()
        self._primary = primary
        self._fallback = fallback
        self.task: PipelineTask | None = None
        self._switched = False

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

    client = make_client()
    audit_client = make_client()

    elevenlabs_key = os.environ["ELEVENLABS_API_KEY"]
    stt = ElevenLabsRealtimeSTTService(api_key=elevenlabs_key)
    tts = ElevenLabsTTSService(api_key=elevenlabs_key, voice_id="SAz9YHcvj6GT2YYXdXww")

    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"])
    llm._client = llm._client.with_options(timeout=httpx.Timeout(8.0, connect=3.0))

    fallback_llm = AnthropicLLMService(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model=os.environ.get("FALLBACK_MODEL", "claude-haiku-4-5"),
    )
    fallback_llm._client = fallback_llm._client.with_options(
        timeout=httpx.Timeout(8.0, connect=3.0)
    )

    llm_switcher = LLMSwitcher(
        llms=[llm, fallback_llm],
        strategy_type=ServiceSwitcherStrategyManual,
    )

    messages = [{"role": "system", "content": build_system_prompt()}]
    context = LLMContext(messages)

    context_aggregator = LLMContextAggregatorPair(
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
            context_aggregator.user(),
            llm_switcher,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    fallback_obs = _LLMFallbackObserver(primary=llm, fallback=fallback_llm)
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[RTVIObserver(rtvi), fallback_obs],
    )
    fallback_obs.task = task

    flow_manager = FlowManager(
        task=task,
        llm=llm_switcher,
        context_aggregator=context_aggregator,
        transport=transport,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client_conn):
        logger.info("Client connected")
        session_id = uuid.uuid4()
        audit = AuditLogger(
            client=audit_client,
            session_id=session_id,
            session_state=flow_manager.state,
            get_transcript=lambda: list(context.messages),
        )
        flow_manager.state["client"] = client
        flow_manager.state["audit"] = audit
        flow_manager.state["session_id"] = str(session_id)
        await audit.start()
        await flow_manager.initialize(create_collect_identity_node(initial=True))

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client_conn):
        logger.info("Client disconnected")
        if not task.has_finished():
            await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    try:
        await runner.run(task)
    finally:
        audit: AuditLogger | None = flow_manager.state.get("audit")
        if audit:
            await audit.finish()
        await client.aclose()
        await audit_client.aclose()


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
