# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI voice agent for scheduling appointments at a health clinic (Prosper Health). The challenge is to build a simple EHR (Electronic Health Record) HTTP API and wire it into the Pipecat-based voice agent.

## Commands

```bash
# Start the full stack (PostgreSQL + API + Frontend + Bot)
docker compose up --build

# Services:
#   http://localhost:8000/docs  — FastAPI EHR (OpenAPI UI)
#   http://localhost:5173       — Vite dashboard
#   http://localhost:7860       — Pipecat bot (click Connect to talk)

# Bot only (without Docker)
uv sync
uv run agent/bot.py

# API type checking / linting
cd api && uv run pyright
uv run ruff check --fix && uv run ruff format
```

First bot run takes ~20 seconds as Pipecat downloads Silero VAD and LocalSmartTurnAnalyzerV3 models.

## Architecture

### Voice pipeline (`bot.py`)

Built on [Pipecat](https://github.com/pipecat-ai/pipecat). The pipeline is a linear chain:

```
WebRTC input → RTVI → ElevenLabs STT → user aggregator → OpenAI LLM → ElevenLabs TTS → WebRTC output → assistant aggregator
```

Key components:
- **Transport**: WebRTC via Daily; the `create_transport` helper picks the right transport from `RunnerArguments`
- **VAD**: Silero VAD with `stop_secs=0.2` detects end-of-speech
- **Turn detection**: `LocalSmartTurnAnalyzerV3` decides when the user has finished their turn (smarter than pure VAD silence)
- **STT**: ElevenLabs Realtime STT (`ElevenLabsRealtimeSTTService`)
- **LLM**: OpenAI via `OpenAILLMService`; conversation state lives in `LLMContext(messages)`
- **TTS**: ElevenLabs (`SAz9YHcvj6GT2YYXdXww` voice)
- **RTVI**: `RTVIProcessor` + `RTVIObserver` exposes a standard real-time voice interface protocol to the browser client

The bot queues an `LLMRunFrame` on `on_client_connected` to trigger the opening greeting. Disconnect cancels the pipeline task.

### EHR API (`api/`)

FastAPI service with five endpoints matching the challenge statement exactly:

| Method | Path | Purpose |
|---|---|---|
| POST | `/create_patient` | Register patient; 409 on duplicate name+DOB |
| GET | `/find_patient` | Lookup by `first_name`, `last_name`, `dob` query params |
| GET | `/list_availability_slots` | Available slots for a `date`; reads `is_booked=false` only |
| POST | `/create_appointment` | Books a slot; flips `is_booked` atomically |
| POST | `/cancel_appointment` | Cancels by `appointment_id`; flips `is_booked` back |

Mutating endpoints require `X-API-Key` header matching `EHR_API_KEY` env var. A `/dashboard` endpoint aggregates stats + recent data for the frontend.

**DB schema key decisions:**
- `availability_slots.is_booked` — denormalized boolean for O(1) availability reads (no join needed)
- Partial unique index `UNIQUE(slot_id) WHERE status='scheduled'` — DB-level double-booking guard
- Compound index `(first_name, last_name, date_of_birth)` — covers `find_patient` exactly

### Dashboard (`frontend/`)

Vite + React + Tailwind. Polls `/dashboard` every 3 seconds. Read-only — no forms. Styled with the Prosper design system tokens from `DESIGN.md`.

### What still needs to be built

1. **LLM tool integration** — register the 5 EHR endpoints as tool calls on `OpenAILLMService` in `bot.py`. In Pipecat this means defining a `ToolCallContext` with function schemas and handling `FunctionCallResultFrame` events.

2. **System prompt** — replace the generic prompt in `messages` with a clinic-specific one guiding the agent through patient identification → registration → scheduling/cancellation.

### Environment

Copy `.env.example` → `.env`:
```
ELEVENLABS_API_KEY=
OPENAI_API_KEY=
EHR_API_KEY=changeme
```

The `DATABASE_URL` is set automatically by `docker-compose.yml` from the `db` service — no need to add it to `.env`.

### Docker

`docker-compose.yml` runs four services: `db` (postgres:16-alpine), `api`, `frontend`, `bot`. The bot uses the existing root `Dockerfile` (`dailyco/pipecat-base`). The API has its own `api/Dockerfile`.
