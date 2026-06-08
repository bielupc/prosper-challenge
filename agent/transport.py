"""Pipecat transport that accepts text input and emits text output."""

import asyncio
from typing import Any, Callable, Optional

from loguru import logger
from pipecat.frames.frames import (
    EndFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.base_transport import BaseTransport
from pipecat.utils.time import time_now_iso8601

_IDLE_GRACE_SECS = 1.5


class TextTransportInput(FrameProcessor):
    """Reads text from an asyncio queue and pushes TranscriptionFrame
    (wrapped in start/stop speaking frames) into the pipeline."""

    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self._queue = queue
        self._task: Optional[asyncio.Task] = None

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            logger.debug("TextTransportInput received StartFrame, starting read task")
            self._task = self.create_task(self._read_input())
        await self.push_frame(frame, direction)

    async def _read_input(self):
        while True:
            text = await self._queue.get()
            if text is None:
                break
            timestamp = time_now_iso8601()
            await self.push_frame(UserStartedSpeakingFrame())
            await self.push_frame(TranscriptionFrame(text=text, user_id="simulation", timestamp=timestamp))
            await self.push_frame(UserStoppedSpeakingFrame())

    async def stop(self, frame: EndFrame):
        self._queue.put_nowait(None)
        if self._task:
            await self.wait_for_task(self._task)
        await super().stop(frame)


class TextTransportOutput(FrameProcessor):
    """Forward the LLM's text as complete messages, and signal when the bot has
    finished its turn (gone idle awaiting user input).
    """

    def __init__(
        self,
        callback: Callable[[str], Any],
        turn_complete: Optional[Callable[[], Any]] = None,
    ):
        super().__init__()
        self._callback = callback
        self._turn_complete = turn_complete
        self._buffer: list[str] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None

    @staticmethod
    async def _cancel(task: Optional[asyncio.Task]):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _flush(self):
        if self._buffer and self._callback:
            text = "".join(self._buffer)
            self._buffer = []
            logger.debug("TextTransportOutput flushing: {}", text)
            await self._callback(text)

    async def _flush_after_idle(self):
        await asyncio.sleep(0.5) 
        await self._flush()

    async def _signal_idle(self):
        await asyncio.sleep(_IDLE_GRACE_SECS)
        if self._turn_complete:
            await self._turn_complete()

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TextFrame):
            self._buffer.append(frame.text)
            await self._cancel(self._idle_task)  # bot is still producing
            await self._cancel(self._flush_task)
            self._flush_task = asyncio.create_task(self._flush_after_idle())
        elif isinstance(frame, LLMFullResponseStartFrame):
            await self._cancel(self._idle_task)  # a new LLM run began — turn not over
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._cancel(self._flush_task)
            await self._flush()  # emit this run's message immediately
            await self._cancel(self._idle_task)
            self._idle_task = asyncio.create_task(self._signal_idle())
        await self.push_frame(frame, direction)


class TextTransport(BaseTransport):
    """Transport that moves text through the Pipecat pipeline.

    Usage:
        transport = TextTransport()
        transport.set_output_callback(lambda text: print("Agent:", text))
        transport.inject_text("Hello")  # from external source (WS, test, etc.)
    """

    def __init__(self, **kwargs):
        super().__init__()
        self._input_queue: asyncio.Queue = asyncio.Queue()
        self._output_callback: Optional[Callable[[str], Any]] = None
        self._turn_complete_callback: Optional[Callable[[], Any]] = None
        self._on_connected: Optional[Callable] = None
        self._on_disconnected: Optional[Callable] = None
        self.session_id: Optional[str] = None

    def set_output_callback(self, callback: Callable[[str], Any]):
        self._output_callback = callback

    def set_turn_complete_callback(self, callback: Callable[[], Any]):
        self._turn_complete_callback = callback

    def inject_text(self, text: str):
        self._input_queue.put_nowait(text)

    def input(self):
        return TextTransportInput(self._input_queue)

    def output(self):
        return TextTransportOutput(self._output_callback, self._turn_complete_callback)
