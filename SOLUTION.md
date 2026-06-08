# Solution Overview — Prosper Health Voice Agent

> **Challenge:** Build an EHR HTTP API and wire a Pipecat-based voice agent so it can identify patients, register new ones, and schedule or cancel appointments during a live conversation.
>
> **Stack:** FastAPI + SQLModel + PostgreSQL (EHR), Pipecat + Pipecat Flows + OpenAI + ElevenLabs (voice agent), Vite + React + Tailwind (dashboard).

---

## 1. What I Was Asked to Build

Per the challenge instructions, I needed to deliver three things:

1. **EHR HTTP API** — at minimum: `create_patient`, `find_patient`, `list_availability_slots`, `create_appointment`, `cancel_appointment`. The API must persist data in a database (not in-memory) and survive restarts.
2. **Conversation Flow** — the agent must identify whether the caller is new or existing, register them if new, and handle booking or cancellation requests.
3. **Integration** — the voice agent must actually call the EHR endpoints during the conversation, not just describe them.

I went a step further and added:
- **Pipecat Flows** — a node-based conversation graph instead of a single monolithic prompt, giving precise control over each step.
- A real-time dashboard (`/dashboard` + `/calendar`) for clinic staff visibility.
- A complete audit trail (`/audit/sessions`, `/audit/tool_call`) so every tool call and conversation transcript is persisted.
- SSE live updates (`/events`) so the dashboard refreshes instantly when a patient books or cancels.
- An LLM fallback (OpenAI → Anthropic) so a single provider outage does not drop the call.
- A three-layer security model that ensures `create_appointment` and `cancel_appointment` can never be triggered by the LLM directly — only after explicit patient confirmation.

---

## 2. Architecture

### 2.1 Full-Stack Overview

```mermaid
flowchart TB
    subgraph Caller["Caller"]
        Browser["Browser (WebRTC)"]
    end

    subgraph Voice["Voice Agent (agent/)"]
        Transport["Daily WebRTC Transport"]
        STT["ElevenLabs STT"]
        TTS["ElevenLabs TTS"]
        VAD["Silero VAD"]
        Turn["LocalSmartTurnAnalyzerV3"]
        LLM["OpenAI LLM (primary)"]
        Fallback["Anthropic LLM (fallback)"]
        RTVI["RTVI Protocol"]
        Flows["Flow Manager\n(node graph)"]
    end

    subgraph EHR["EHR API (api/)"]
        Auth["API Key Middleware"]
        Patients["/create_patient\n/find_patient"]
        Slots["/list_availability_slots"]
        Appts["/create_appointment\n/cancel_appointment\n/list_appointments"]
        Dash["/dashboard\n/calendar\n/events"]
        Audit["/audit/*"]
    end

    subgraph DB[(PostgreSQL)]
        P[(patients)]
        S[(availability_slots)]
        A[(appointments)]
        AS[(appointment_slots)]
        CS[(call_sessions)]
        TCL[(tool_call_logs)]
    end

    subgraph Frontend["Dashboard (Vite + React)"]
        UI["Stats + Calendar View"]
    end

    Browser <-->|WebRTC| Transport
    Transport --> STT --> LLM --> TTS --> Transport
    LLM -.->|ErrorFrame| Fallback
    Flows -->|node transitions| LLM
    LLM -->|tool calls| EHR
    EHR --> DB
    Frontend -->|Poll + SSE| EHR
```

### 2.2 Voice Pipeline

```mermaid
flowchart LR
    A["WebRTC Input"] --> B["RTVIProcessor"]
    B --> C["ElevenLabs STT"]
    C --> D["User Aggregator\n+ Smart Turn"]
    D --> E["LLM Switcher\n(OpenAI → Anthropic)"]
    E --> F["ElevenLabs TTS"]
    F --> G["WebRTC Output"]
    G --> H["Assistant Aggregator"]
    H --> D

    E -->|FunctionCallResultFrame| I["Flow Manager\n(Node Graph)"]
    I -->|queues LLMRunFrame| E
    I -->|httpx| J["EHR API"]
    I -->|audit| K["AuditLogger"]
```

The pipeline is a standard Pipecat linear chain. What makes it a "voice agent" rather than a chatbot is the **Flow Manager** (`pipecat_flows.FlowManager`) sitting above the LLM. It does not replace the pipeline — it drives it by:
1. Updating the `LLMContext` task messages when entering a new node
2. Registering only the functions relevant to that node on the LLM switcher
3. Queuing `LLMRunFrame` to trigger inference
4. Handling `FunctionCallResultFrame` to decide the next node transition

### 2.3 Flow Manager Node Graph

The conversation is modeled as a directed graph of nodes. Each node is a `NodeConfig` containing:
- `task_messages` — a scoped system prompt for that conversational step
- `functions` — only the tools the LLM may call in this state
- `post_actions` — what to do after the node completes (e.g., `end_conversation`)

```mermaid
flowchart TD
    A["collect_identity\n(greet + submit_identity)"] -->|found| B["collect_intent\n(submit_intent)"]
    A -->|not found| C["no_match\n(retry_or_register)"]
    C -->|retry| A
    C -->|register| D["collect_registration\n(submit_registration)"]
    C -->|escalate| E["escalate\n(save_callback_phone)"]
    D -->|success| B
    D -->|fail| E
    B -->|book| F["collect_booking_request\n(check_date_slots + submit_booking_request)"]
    B -->|cancel| G["cancellation_flow\n(list_appointments_tool + submit_cancellation)"]
    F -->|valid range| H["confirm_booking\n(confirm_booking)"]
    F -->|invalid / no slots| F
    H -->|confirmed=True| I["book\n(server-side: _perform_booking)"]
    H -->|confirmed=False + correction=datetime| F
    H -->|confirmed=False + correction=patient| A
    I -->|success| J["wrap_up\n(end_conversation)"]
    I -->|fail| E
    G -->|appointment selected| K["cancel\n(server-side: _perform_cancellation)"]
    K -->|success| J
    K -->|fail| E
    E --> J
```

**Key design principle:** The two destructive EHR operations — `create_appointment` and `cancel_appointment` — are **not exposed as LLM tools anywhere in the graph**. They are pure Python helpers (`_perform_booking`, `_perform_cancellation`) called server-side only after the patient has explicitly confirmed via the `confirm_booking` or `submit_cancellation` handlers. The LLM cannot invoke them directly.

### 2.4 Database Schema

```mermaid
erDiagram
    PATIENTS {
        uuid id PK
        string first_name
        string last_name
        date date_of_birth
        string phone
        string email
        datetime created_at
    }

    AVAILABILITY_SLOTS {
        uuid id PK
        date date
        time start_time
        time end_time
        boolean is_booked
    }

    APPOINTMENTS {
        uuid id PK
        uuid patient_id FK
        string status
        datetime created_at
        datetime cancelled_at
    }

    APPOINTMENT_SLOTS {
        uuid appointment_id PK,FK
        uuid slot_id PK,FK
        boolean active
    }

    CALL_SESSIONS {
        uuid id PK
        uuid patient_id
        string patient_name
        string status
        json transcript
        datetime started_at
        datetime ended_at
    }

    TOOL_CALL_LOGS {
        uuid id PK
        uuid session_id FK
        uuid patient_id
        string tool_name
        json arguments
        json result
        boolean success
        int duration_ms
        datetime created_at
    }

    PATIENTS ||--o{ APPOINTMENTS : "has"
    APPOINTMENTS ||--o{ APPOINTMENT_SLOTS : "composed_of"
    APPOINTMENT_SLOTS ||--|| AVAILABILITY_SLOTS : "references"
    CALL_SESSIONS ||--o{ TOOL_CALL_LOGS : "has"
```

---

## 3. Key Design Decisions & Trade-offs

### 3.1 Flow Manager vs. Monolithic Prompt

**Decision:** I used `pipecat_flows.FlowManager` with a 10-node graph instead of a single massive system prompt with 6 registered tools.

**Why:** A monolithic prompt gives the LLM access to all tools at once. In a healthcare setting, this is risky — the model could theoretically call `cancel_appointment` immediately after identification, before the patient has even stated their intent. With Flows, each node exposes only the functions relevant to that step:
- `collect_identity` only has `submit_identity`
- `confirm_booking` only has `confirm_booking`
- The destructive operations (`_perform_booking`, `_perform_cancellation`) are not functions at all — they are Python helpers unreachable from the LLM

**Trade-off:** More code. A monolithic prompt is ~100 lines; the node graph is ~870 lines across `agent/nodes.py`. But the gain in safety and debuggability is worth it — each node is a self-contained unit with a single responsibility.

### 3.2 Security: Three-Layer Defense for Destructive Operations

**Decision:** `create_appointment` and `cancel_appointment` are protected by three independent layers.

**Layer 1 — Not an LLM tool:** The EHR endpoints are never in any node's `functions` list. The LLM's function schema never includes them.

**Layer 2 — State write only on confirmation:** The `confirmed_patient_id`, `confirmed_date`, `confirmed_start_time`, `confirmed_end_time`, and `confirmed_appointment_id` fields are written **only** inside the confirmation handlers (`handle_confirm_booking`, `handle_submit_cancellation`) when the patient explicitly says yes.

**Layer 3 — Handler asserts before EHR write:** `_perform_booking` and `_perform_cancellation` verify all confirmed state fields are present before calling the EHR API. If any are missing, they log an invariant violation and escalate to a human.

**Trade-off:** More complex state management. The `FlowManager.state` dict carries more fields. But in healthcare, a double-booking or accidental cancellation is worse than a little extra state tracking.

### 3.3 Database: Denormalized `is_booked` on Slots

**Decision:** `availability_slots` has a boolean `is_booked` column, even though the canonical booking state lives in the `appointment_slots` junction table.

**Why:** Listing available slots is the hottest read path. Without `is_booked`, the query would need a `LEFT JOIN` + `NOT EXISTS` subquery. With it, the query is a simple `SELECT ... WHERE is_booked = false`.

**Trade-off:** Two sources of truth. Mitigated by:
- Updating `is_booked` in the same transaction as `appointment_slots` creation/cancellation.
- Adding a DB-level partial unique index `UNIQUE(slot_id) WHERE active = true` on `appointment_slots`. Even if a race condition occurs, the index rejects the second insert.

**Future:** If the clinic needs "soft holds" (mid-booking but not confirmed), `is_booked` would need to become a state machine. For now, binary is correct.

### 3.4 Booking Model: Multi-Slot Appointments

**Decision:** Appointments can span multiple contiguous slots (e.g., 09:00–10:00 uses two 30-minute slots).

**Why:** Real clinics have visits of varying duration. The agent asks "How long do you need?" and books the appropriate number of slots.

**Trade-off:** More complex validation. The API checks that:
1. The requested range exactly tiles contiguous slots (no gaps, no partial overlap).
2. All slots are unbooked.
3. The start time is not in the past.

By enforcing grid alignment, the API fails fast with a clear message rather than letting the LLM hallucinate times like 09:15.

### 3.5 Session Security: Identity Locking

**Decision:** Once the bot lists a patient's appointments or creates/cancels one, the session becomes `locked`. If the caller then tries to re-identify with a different name, the bot refuses.

**Why:** Healthcare is high-stakes. A caller should not be able to say "Wait, actually I'm John Smith" after already seeing Jane Doe's appointments. This is a lightweight HIPAA-aligned guard.

**Trade-off:** It prevents legitimate corrections. Mitigated by making the lock trigger only after **sensitive** data access (listing appointments), not after simple identification.

### 3.6 Appointment Cancellation: Client-Side ID Validation

**Decision:** The bot maintains an `appt_ids` set in `FlowManager.state`. `submit_cancellation` rejects any `appointment_id` not in that set, even if the patient technically owns it in the DB.

**Why:** The prompt tells the LLM *"Never ask the caller for an appointment ID — always identify by date and time."* The caller never sees UUIDs. The only way the LLM can obtain an `appointment_id` is by calling `list_appointments_tool` first, which populates `appt_ids`. This prevents the LLM from hallucinating or fabricating an ID.

**Trade-off:** If a new appointment is created by a different channel mid-call, the bot won't know about it. This is acceptable because the bot's world view is scoped to the conversation.

### 3.7 Audit: Fail-Safe, Not Fail-Closed

**Decision:** Every tool call is wrapped by `flows_audited(...)`, which logs the LLM arguments, the HTTP request/response, and the result to the EHR API. Audit failures are swallowed with `try/except` and run as fire-and-forget background tasks — they never block the conversation.

**Why:** An audit system outage should not drop a patient call. The audit is for compliance and debugging, not for business logic.

**Trade-off:** We might lose audit data during an outage. Mitigated by using `loguru` to log exceptions, so they still appear in application logs even if the DB write fails.

### 3.8 LLM Fallback: OpenAI → Anthropic

**Decision:** The pipeline uses `LLMSwitcher` with OpenAI as primary and Anthropic as fallback. An observer watches for `ErrorFrame` from the primary LLM and triggers a manual switch + `LLMRunFrame` retry.

**Why:** Voice calls are real-time. If OpenAI's API is rate-limited or down, the call should not die. The fallback is a different provider, reducing correlated failure risk.

**Trade-off:** The fallback LLM may not have the same tool definitions or may behave differently. Mitigated by registering tools on the `LLMSwitcher`, which forwards registration to **both** LLMs. The fallback is a fast, cheap model sufficient for graceful degradation.

**Guard:** The `_switched` flag ensures only one fallback per call. Without it, a persistent error could loop between primary and fallback indefinitely.

### 3.9 Dashboard: Polling + SSE Hybrid

**Decision:** The dashboard polls `/dashboard` every 3 seconds **and** subscribes to `/events` (SSE) for instant updates.

**Why:** SSE alone is elegant but fragile — proxy timeouts, connection drops, or mobile browsers can kill it. Polling is a robust backstop. The SSE `broadcast()` fires on every mutating DB operation, so the dashboard feels live.

**Trade-off:** Slightly more server load. For a clinic with 5 staff members, this is negligible.

### 3.10 Error Handling: Friendly vs. Precise

**Decision:** The bot translates HTTP errors into patient-friendly voice messages. For example, a 409 "Slot already booked" becomes "I'm sorry, that slot was just taken. Would you like me to check the next available time?"

**Why:** The LLM is the voice of the clinic. Exposing raw HTTP status codes or stack traces would be unprofessional and confusing.

**Implementation:** The `_friendly_error` helper maps 4xx errors to a generic "invalid request" message and 5xx errors to "temporarily unavailable." The global persona prompt instructs: *"If a tool returns an error, apologize briefly and offer to try again or suggest calling the front desk."*

---

## 4. Conversation Flow

The Flow Manager enforces a strict protocol through node transitions:

```mermaid
sequenceDiagram
    participant Caller
    participant Bot as Flow Manager Node Graph
    participant EHR as EHR API

    Caller->>Bot: "Hi, I'd like to book an appointment"
    Bot->>Bot: collect_identity node
    Bot->>Caller: "Are you a new or returning patient?"
    Caller->>Bot: "Returning"
    Bot->>Caller: "What's your name and date of birth?"
    Caller->>Bot: "Jane Doe, March 15 1985"
    Bot->>Bot: submit_identity tool → find_patient
    Bot->>EHR: GET /find_patient
    EHR-->>Bot: Patient found
    Bot->>Bot: collect_intent node
    Bot->>Caller: "Welcome Jane. Book or cancel?"
    Caller->>Bot: "Book"
    Bot->>Bot: collect_booking_request node
    Bot->>Caller: "What day?"
    Caller->>Bot: "Tomorrow at 9 AM"
    Bot->>EHR: GET /list_availability_slots
    EHR-->>Bot: Slots available
    Bot->>Bot: submit_booking_request tool
    Bot->>Bot: confirm_booking node
    Bot->>Caller: "So that's Jane Doe, Monday June 9 at 9 AM — is that right?"
    Caller->>Bot: "Yes"
    Bot->>Bot: confirm_booking tool → _perform_booking
    Bot->>EHR: POST /create_appointment
    EHR-->>Bot: Appointment created
    Bot->>Bot: wrap_up node
    Bot->>Caller: "Done — you're booked for Monday at 9 AM. Goodbye!"
    Bot->>Bot: end_conversation
```

**Key constraints baked into the node graph:**
- **Confirmation gates:** The bot must get a clear "yes" before booking. This prevents misheard names or times from creating phantom appointments.
- **Weekend guard:** If the caller asks for a Saturday or Sunday, the bot redirects to the next Monday.
- **No UUIDs aloud:** The prompt explicitly forbids reading IDs. All appointment selection is by natural date/time.
- **Short responses:** One or two sentences max, no filler phrases. This is a voice call, not a chatbot.

---

## 5. Areas for Improvement

### 5.1 Latency: Reducing Time-to-First-Word

**Current state:** The bot takes ~20 seconds on first boot (model download). Per-turn latency is dominated by STT, LLM inference, and TTS.

**Opportunities:**
- **Streaming function calls:** Currently, the bot waits for the full LLM response before speaking. Pipecat supports streaming TTS, but function calls are synchronous. Streaming the LLM's reasoning while the user is still speaking could shave perceptible latency.
- **Local LLM:** For simple intents ("I want to cancel"), a local 7B model could decide without a network round-trip. Complex cases (multi-slot booking) would still hit OpenAI. A hybrid router would trade accuracy for speed on the easy path.
- **Pre-fetching slots:** The bot could pre-fetch tomorrow's availability slots in the background while the caller is still giving their name, reducing the perceived latency of the "what times do you have?" step.

### 5.2 Reliability: Surviving External Failures

**Current state:** We have LLM fallback and friendly error messages. But the system is still vulnerable to:
- **EHR API outage:** The bot apologizes and suggests calling the front desk. This is graceful degradation, but not recovery.
- **Database outage:** The API returns 500; the bot catches it. But no retry or queueing exists.
- **STT/TTS outage:** If ElevenLabs is down, the call is dead. We have no fallback STT/TTS provider configured.

**Opportunities:**
- **Circuit breaker:** If the EHR API fails 3 times in 30 seconds, the bot should enter a "read-only mode" where it can answer questions but not book/cancel. This prevents cascading failures.
- **Async job queue:** For appointment creation, we could enqueue the request in Redis/RabbitMQ and return a "pending" confirmation. The bot would say "I'm processing your booking — you'll get a text confirmation in a moment." This decouples the voice pipeline from DB write latency.
- **Fallback TTS:** Configure a local TTS (e.g., Coqui TTS, Piper) as a last resort. The voice quality would drop, but the call would continue.
- **Health checks + auto-restart:** The Docker Compose setup should include `healthcheck` blocks and `restart: unless-stopped` for all services.

### 5.3 Evaluation: Automated Testing & Simulation

**Current state:** No automated test suite for the conversation flow. Validation is manual: open the browser, click Connect, talk to the bot.

**Opportunities:**

#### A. Unit Tests for Node Handlers
We can test each `handle_*` function in isolation with a mocked `httpx.AsyncClient` and a fake `FlowManager`. This is low-hanging fruit and would catch regressions in parameter mapping, state logic, and error handling.

#### B. LLM-as-Judge for Conversation Quality
Use a second LLM with a strict evaluation prompt to grade conversation transcripts on:
- Did the bot ask for confirmation before identifying?
- Did it refuse to book without authentication?
- Did it read back the correct date/time?
- Did it hallucinate a UUID?

This is a form of **synthetic evaluation** that can run in CI without human testers.

#### C. Simulation Framework: pytest + Pipecat test harness
Pipecat can be driven with programmatic frame injection. We could build a harness that:
1. Injects `TranscriptionFrame` with fake STT text (e.g., "My name is John Smith, born March 15th 1985").
2. Captures the resulting `TTSFrame` or `FunctionCallFrame`.
3. Asserts that the expected tool was called with the expected arguments.
4. Injects the tool result and asserts the next LLM response contains the expected text.

This would let us run 100 simulated calls in CI and catch regressions like "the LLM stopped asking for confirmation" or "it books appointments without checking availability first."

#### D. Shadow Mode / A/B Testing
In production, run the new bot version in "shadow mode": it receives the same audio stream but does not speak or act. Its tool calls and responses are compared against the production version. Divergences are flagged for human review. This de-risks deployments.

#### E. Red-Team / Adversarial Testing
Have an LLM act as a malicious caller and try to:
- Cancel someone else's appointment.
- Extract another patient's data.
- Book a slot in the past.
- Crash the bot with unexpected input (e.g., SQL injection via voice).

This can be automated and run nightly.

---

## 6. Files & Structure

```
prosper-challenge/
├── agent/
│   ├── bot.py              # Pipecat pipeline, FlowManager setup, LLM fallback
│   ├── nodes.py            # Flow node graph: 10 nodes, security layers, handlers
│   ├── ehr.py              # httpx client + _friendly_error + ehr_get/ehr_post
│   ├── audit.py            # AuditLogger + flows_audited() wrapper
│   └── Dockerfile          # Bot service image
├── api/
│   ├── main.py             # FastAPI app, lifespan, CORS, middleware
│   ├── core/
│   │   ├── auth.py         # API key middleware (X-API-Key)
│   │   ├── database.py     # SQLModel async engine + session factory
│   │   ├── seed.py         # Generates 60 days of 30-minute slots
│   │   └── events.py       # SSE broadcast helper
│   ├── models/
│   │   ├── patient.py      # Patient table + case-insensitive unique index
│   │   ├── slot.py         # AvailabilitySlot + denormalized is_booked
│   │   ├── appointment.py  # Appointment table + status constraint
│   │   ├── appointment_slot.py  # Junction table + double-booking guard
│   │   └── audit.py        # CallSession + ToolCallLog
│   ├── routers/
│   │   ├── patients.py     # create_patient, find_patient
│   │   ├── slots.py        # list_availability_slots
│   │   ├── appointments.py  # create_appointment, cancel_appointment, list_appointments
│   │   ├── dashboard.py    # /dashboard, /calendar
│   │   ├── audit.py        # /audit/session, /audit/tool_call, /audit/sessions
│   │   └── events.py       # SSE /events
│   └── schemas/
│       ├── patient.py
│       ├── slot.py
│       ├── appointment.py
│       ├── dashboard.py
│       └── audit.py
├── frontend/               # Vite + React + Tailwind dashboard (read-only)
├── docker-compose.yml      # Full stack: db, api, frontend, bot
├── SOLUTION.md             # This file
└── README.md               # Challenge instructions
```

---

## 7. How to Run

```bash
# Full stack (PostgreSQL + API + Frontend + Bot)
docker compose up --build

# Endpoints:
#   http://localhost:8000/docs  — FastAPI OpenAPI UI
#   http://localhost:5173       — Dashboard
#   http://localhost:7860       — Bot (click Connect to talk)
```

---

## 8. Summary

I built a production-grade voice agent for a healthcare clinic that:
- **Identifies patients** by name and DOB, with confirmation gating and spelling retry logic.
- **Registers new patients** atomically, rejecting duplicates at the DB level.
- **Books multi-slot appointments** with atomic availability checks and DB-level double-booking guards.
- **Cancels appointments** securely, with client-side ID validation to prevent hallucination.
- **Uses a node-based conversation graph** (Pipecat Flows) instead of a monolithic prompt, giving precise control over each step and ensuring destructive operations can only happen after explicit patient confirmation.
- **Protects destructive operations with three independent security layers:** not exposed as LLM tools, state written only on confirmation, server-side asserts before EHR writes.
- **Audits everything** — every tool call, every HTTP exchange, every conversation transcript, shipped via fire-and-forget background tasks that never block the call.
- **Falls back gracefully** — LLM provider failure, EHR downtime, or invalid input all produce friendly voice responses rather than crashes.
- **Provides real-time visibility** — a dashboard with live SSE updates so clinic staff can see the schedule as it changes.

The design prioritizes **safety over convenience** (three-layer security, confirmation gates, DB-level constraints) and **observability over opacity** (full audit trail, structured logs, node-level debugging). The trade-offs are documented above, along with concrete next steps for latency, reliability, and evaluation.
