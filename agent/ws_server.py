"""WebSocket server that exposes the bot in text-only mode for simulations."""

import asyncio
import json
import os

import websockets
from bot import run_text_bot
from dotenv import load_dotenv
from loguru import logger
from pipecat.runner.types import RunnerArguments
from transport import TextTransport

load_dotenv(override=True)

SIM_WS_PORT = int(os.environ.get("SIMULATION_WS_PORT", "7861"))


class SimConnection:
    def __init__(self, websocket):
        self.websocket = websocket
        self.transport = TextTransport()
        self.bot_task: asyncio.Task | None = None
        self._closed = False

    async def run(self):
        # Start the real Pipecat pipeline in the background
        self.transport.set_output_callback(self._send_agent_message)
        self.transport.set_turn_complete_callback(self._send_idle)

        ready = asyncio.Event()
        self.bot_task = asyncio.create_task(
            run_text_bot(
                self.transport,
                RunnerArguments(),
                ready_event=ready,
            )
        )

        await ready.wait()
        logger.info("Text-mode pipeline ready — initialising flow")
        if self.transport._on_connected:
            await self.transport._on_connected()

        if self.transport.session_id:
            await self.websocket.send(
                json.dumps(
                    {"role": "system", "event": "session", "session_id": self.transport.session_id}
                )
            )

        # Watch for the pipeline to finish on its own (end_conversation)
        pipeline_done = asyncio.create_task(self._wait_for_pipeline())

        # Drive the conversation
        try:
            async for raw in self.websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("role") == "user" and "text" in msg:
                    self.transport.inject_text(msg["text"])
                elif msg.get("role") == "system" and msg.get("event") == "disconnect":
                    break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            pipeline_done.cancel()
            try:
                await pipeline_done
            except asyncio.CancelledError:
                pass
            await self._close()

    async def _wait_for_pipeline(self):
        """Wait for the bot pipeline task to finish, then signal completion."""
        if not self.bot_task:
            return
        try:
            await self.bot_task
        except asyncio.CancelledError:
            return
        logger.info("Pipeline finished naturally — signalling completion")
        try:
            await self.websocket.send(
                json.dumps({"role": "system", "event": "finished"})
            )
        except Exception:
            pass

    async def _send_agent_message(self, text: str):
        if self._closed:
            return
        payload = json.dumps({"role": "agent", "text": text})
        try:
            await self.websocket.send(payload)
        except websockets.exceptions.ConnectionClosed:
            pass

    async def _send_idle(self):
        """Tell the client the bot finished its turn and is awaiting user input."""
        if self._closed:
            return
        try:
            await self.websocket.send(json.dumps({"role": "system", "event": "idle"}))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def _close(self):
        if self._closed:
            return
        self._closed = True
        logger.info("Closing simulation connection")

        if self.transport._on_disconnected:
            try:
                await self.transport._on_disconnected()
            except Exception:
                pass

        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
            try:
                await self.bot_task
            except asyncio.CancelledError:
                pass

        try:
            await self.websocket.send(
                json.dumps({"role": "system", "event": "finished"})
            )
        except Exception:
            pass
        try:
            await self.websocket.close()
        except Exception:
            pass


async def handler(websocket):
    logger.info("Simulation WS client connected from {}", websocket.remote_address)
    conn = SimConnection(websocket)
    await conn.run()


async def main():
    logger.info("Starting simulation WebSocket server on port {}", SIM_WS_PORT)
    async with websockets.serve(handler, "0.0.0.0", SIM_WS_PORT):
        await asyncio.Future() 


if __name__ == "__main__":
    asyncio.run(main())
