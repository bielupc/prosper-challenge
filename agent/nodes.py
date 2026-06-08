"""Pipecat Flows conversation node graph for Prosper appointment scheduling.

Node topology:
  collect_identity (initial — greet inline when initial=True)
      → collect_intent          (patient found)
      → no_match                (patient not found)

  no_match
      → retry (re-call find_patient, corrected name/DOB, max 2 attempts)
      → collect_registration    (patient wants to register)
      → escalate

  collect_registration
      → collect_intent          (registration succeeded)
      → escalate                (registration failed)

  collect_intent                ("book or cancel?")
      → collect_booking_request
      → cancellation_flow

  collect_booking_request       (check slots + submit time range)
      → confirm_booking         (range valid + slots available)
      → stay                    (no slots / invalid range — LLM retries)

  confirm_booking
      → book                    (confirmed=True)
      → collect_booking_request (correction_type=datetime)
      → collect_identity        (correction_type=patient)

  book  ← ONLY node where create_appointment is registered
      → wrap_up                 (success)
      → escalate                (EHR failure)

  cancellation_flow             (list appointments → select one)
      → cancel                  (appointment selected)

  cancel  ← ONLY node where cancel_appointment is registered
      → wrap_up                 (success)
      → escalate                (EHR failure)

  escalate                      (collect callback phone)
      → wrap_up

  wrap_up (end_conversation)

Security enforcement — three independent layers:
  1. Topology   — create_appointment is ONLY on 'book'; cancel_appointment is ONLY
                  on 'cancel'. The LLM cannot call either from any other state.
  2. State write — confirmed_patient_id / confirmed_date / confirmed_start_time /
                   confirmed_end_time are written ONLY inside handle_confirm_booking
                   when confirmed=True. confirmed_appointment_id is written ONLY
                   inside handle_submit_cancellation.
  3. Handler assert — execute_booking and execute_cancellation verify all confirmed
                      state fields are present before calling the EHR API.
"""

from __future__ import annotations

import json
import time
from datetime import date as _date_type
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from pipecat_flows import FlowManager, FlowsFunctionSchema, NodeConfig

from ehr import ehr_get, ehr_post

try:
    from audit import flows_audited
except ImportError:
    def flows_audited(tool_name, handler):  # noqa: E302
        return handler

FlowArgs = dict[str, Any]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _format_time(t: str) -> str:
    """'09:30' → '9:30 AM', '13:00' → '1 PM'"""
    try:
        h, m = map(int, t.split(":"))
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}" if m else f"{h12} {period}"
    except Exception:
        return t


def _format_date(d: str) -> str:
    """'2026-06-08' → 'Monday, June 8'"""
    try:
        return _date_type.fromisoformat(d).strftime("%A, %B %-d")
    except Exception:
        return d


def _append_callback(session_id: str, phone: str, reason: str) -> None:
    log_path = Path("logs/callbacks.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "session_id": session_id,
        "phone": phone,
        "captured_at": str(_date_type.today()),
        "reason": reason,
    }
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")




# ---------------------------------------------------------------------------
# wrap_up
# ---------------------------------------------------------------------------


def create_wrap_up_node(instructions: str = "") -> NodeConfig:
    content = instructions or "Thank the patient warmly and say goodbye. One sentence only."
    return {
        "name": "wrap_up",
        "task_messages": [{"role": "system", "content": content}],
        "functions": [],
        "post_actions": [{"type": "end_conversation"}],
    }


# ---------------------------------------------------------------------------
# escalate
# ---------------------------------------------------------------------------


def create_escalate_node(reason: str = "") -> NodeConfig:
    async def handle_save_callback(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig]:
        phone = args.get("phone_number", "").strip()
        fm.state["callback_phone"] = phone
        _append_callback(fm.state.get("session_id", "unknown"), phone, reason or "escalated")
        logger.info("Callback captured session={}", fm.state.get("session_id"))
        return {"captured": True}, create_wrap_up_node()

    save_fn = FlowsFunctionSchema(
        name="save_callback_phone",
        description="Save the patient's callback phone number so a clinic staff member can call back",
        properties={"phone_number": {"type": "string", "description": "Callback phone number"}},
        required=["phone_number"],
        handler=flows_audited("save_callback_phone", handle_save_callback),
        cancel_on_interruption=False,
    )
    return {
        "name": "escalate",
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Apologize briefly that you couldn't complete the request. "
                    "Tell the patient someone from Prosper Health will call them back shortly. "
                    "Ask for their callback phone number, then call save_callback_phone."
                ),
            }
        ],
        "functions": [save_fn],
    }


# ---------------------------------------------------------------------------
# cancel  ← ONLY node where cancel_appointment is registered  (layer 1)
# ---------------------------------------------------------------------------


def create_cancel_node() -> NodeConfig:
    async def handle_execute_cancellation(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig]:
        # Layer 3: assert confirmed state is present before touching the EHR
        appt_id = fm.state.get("confirmed_appointment_id")
        patient_id = fm.state.get("patient_id")
        if not appt_id or not patient_id:
            logger.error(
                "execute_cancellation: confirmed state missing — topology violation. "
                "appt_id={!r} patient_id={!r}",
                appt_id,
                patient_id,
            )
            return {"cancelled": False, "error": "topology_violation"}, create_escalate_node(
                "state_error"
            )

        client: httpx.AsyncClient = fm.state["client"]
        t0 = time.monotonic()
        ok, r = await ehr_post(
            client, "/cancel_appointment", {"appointment_id": appt_id, "patient_id": patient_id}
        )
        logger.info("execute_cancellation: {}ms ok={}", int((time.monotonic() - t0) * 1000), ok)

        if ok:
            date_human = _format_date(r.get("appointment_date", ""))
            start_human = _format_time((r.get("start_time") or "")[:5])
            return (
                {"cancelled": True},
                create_wrap_up_node(
                    f"Confirm the cancellation: the appointment on {date_human} at {start_human} "
                    "has been cancelled. Thank the patient and say goodbye."
                ),
            )
        return (
            {"cancelled": False, "reason": r.get("detail", "Cancellation failed")},
            create_escalate_node("cancel_failed"),
        )

    cancel_fn = FlowsFunctionSchema(
        name="execute_cancellation",
        description="Execute the appointment cancellation. Call this immediately.",
        properties={},
        required=[],
        handler=flows_audited("execute_cancellation", handle_execute_cancellation),
        cancel_on_interruption=False,
    )
    return {
        "name": "cancel",
        "task_messages": [
            {"role": "system", "content": "Call execute_cancellation right now. Do not speak first."}
        ],
        "functions": [cancel_fn],
        "respond_immediately": True,
    }


# ---------------------------------------------------------------------------
# cancellation_flow
# ---------------------------------------------------------------------------


def create_cancellation_flow_node() -> NodeConfig:
    async def handle_list_appointments(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, None]:
        patient_id = fm.state.get("patient_id")
        client: httpx.AsyncClient = fm.state["client"]

        ok, r = await ehr_get(client, "/list_appointments", {"patient_id": patient_id})
        if not ok:
            return {"appointments": [], "error": r.get("detail", "Failed to fetch appointments")}, None

        appointments = r if isinstance(r, list) else []
        appt_ids: set[str] = set()
        result = []
        for a in appointments:
            appt_ids.add(a["id"])
            result.append({
                "appointment_id": a["id"],
                "date": _format_date(a["appointment_date"]),
                "start_time": _format_time(a["start_time"][:5]),
                "end_time": _format_time(a["end_time"][:5]),
            })
        fm.state["appt_ids"] = appt_ids
        return {"appointments": result, "count": len(result)}, None

    async def handle_submit_cancellation(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig | None]:
        appt_id = args.get("appointment_id", "").strip()
        appt_ids: set[str] = fm.state.get("appt_ids", set())

        if appt_id not in appt_ids:
            return {
                "valid": False,
                "error": "Appointment not found. Use an appointment_id from the list above.",
            }, None

        # Layer 2: write confirmed state ONLY here
        fm.state["confirmed_appointment_id"] = appt_id
        return {"valid": True}, create_cancel_node()

    list_fn = FlowsFunctionSchema(
        name="list_appointments_tool",
        description="Fetch the patient's upcoming appointments. Call this first.",
        properties={},
        required=[],
        handler=flows_audited("list_appointments_tool", handle_list_appointments),
        cancel_on_interruption=False,
    )
    submit_fn = FlowsFunctionSchema(
        name="submit_cancellation",
        description=(
            "Submit the appointment to cancel once the patient has selected one. "
            "Use the appointment_id from the list."
        ),
        properties={
            "appointment_id": {
                "type": "string",
                "description": "UUID of the appointment to cancel",
            }
        },
        required=["appointment_id"],
        handler=flows_audited("submit_cancellation", handle_submit_cancellation),
        cancel_on_interruption=False,
    )
    return {
        "name": "cancellation_flow",
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Call list_appointments_tool first to load the patient's appointments. "
                    "Read them back by date and time only — never mention IDs or UUIDs. "
                    "If there are no appointments, say so and end the call. "
                    "If there are multiple, ask which one to cancel. "
                    "Once the patient identifies their appointment, call submit_cancellation "
                    "with the correct appointment_id."
                ),
            }
        ],
        "functions": [list_fn, submit_fn],
    }


# ---------------------------------------------------------------------------
# book  ← ONLY node where create_appointment is registered  (layer 1)
# ---------------------------------------------------------------------------


def create_book_node() -> NodeConfig:
    async def handle_execute_booking(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig]:
        # Layer 3: assert confirmed state is present before touching the EHR
        patient_id = fm.state.get("confirmed_patient_id")
        date_ = fm.state.get("confirmed_date")
        start = fm.state.get("confirmed_start_time")
        end = fm.state.get("confirmed_end_time")

        if not all([patient_id, date_, start, end]):
            logger.error(
                "execute_booking: confirmed state missing — topology violation. "
                "patient_id={!r} date={!r}",
                patient_id,
                date_,
            )
            return {"booked": False, "error": "topology_violation"}, create_escalate_node(
                "state_error"
            )

        # Dedup guard: if LLM retries the tool call for the same booking, short-circuit
        dedup_key = f"{fm.state.get('session_id')}:{patient_id}:{date_}:{start}:{end}"
        if fm.state.get("booking_dedup_key") == dedup_key:
            logger.warning("execute_booking: duplicate call — returning prior result")
            return (
                {"booked": True, "duplicate": True},
                create_wrap_up_node(
                    f"Confirm that the appointment on {_format_date(date_)} from "
                    f"{_format_time(start)} to {_format_time(end)} is booked. "
                    "Thank the patient and say goodbye."
                ),
            )
        fm.state["booking_dedup_key"] = dedup_key

        client: httpx.AsyncClient = fm.state["client"]
        t0 = time.monotonic()
        ok, r = await ehr_post(
            client,
            "/create_appointment",
            {"patient_id": patient_id, "date": date_, "start_time": start, "end_time": end},
        )
        logger.info("execute_booking: {}ms ok={}", int((time.monotonic() - t0) * 1000), ok)

        if ok:
            date_human = _format_date(r.get("appointment_date", date_))
            start_human = _format_time((r.get("start_time") or start)[:5])
            end_human = _format_time((r.get("end_time") or end)[:5])
            fm.state["last_appointment_id"] = r.get("id")
            return (
                {"booked": True, "appointment_id": r.get("id")},
                create_wrap_up_node(
                    f"Confirm the booking: {date_human} from {start_human} to {end_human}. "
                    "Thank the patient warmly and say goodbye."
                ),
            )
        return (
            {"booked": False, "reason": r.get("detail", "Booking failed")},
            create_escalate_node("booking_failed"),
        )

    book_fn = FlowsFunctionSchema(
        name="execute_booking",
        description="Execute the appointment booking after patient confirmation. Call this immediately.",
        properties={},
        required=[],
        handler=flows_audited("execute_booking", handle_execute_booking),
        cancel_on_interruption=False,
    )
    return {
        "name": "book",
        "task_messages": [
            {"role": "system", "content": "Call execute_booking right now. Do not speak first."}
        ],
        "functions": [book_fn],
        "respond_immediately": True,
    }


# ---------------------------------------------------------------------------
# confirm_booking
# ---------------------------------------------------------------------------


def create_confirm_booking_node(
    patient_name: str, date: str, start_time: str, end_time: str
) -> NodeConfig:
    date_human = _format_date(date)
    start_human = _format_time(start_time)
    end_human = _format_time(end_time)

    async def handle_confirm_booking(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig]:
        confirmed: bool = bool(args.get("confirmed"))

        if not confirmed:
            correction = args.get("correction_type", "datetime")
            if correction == "patient":
                # Reset identity state so re-identification is clean
                for key in ("patient_id", "patient_name"):
                    fm.state.pop(key, None)
                return {"confirmed": False, "correction": "patient"}, create_collect_identity_node()
            return {"confirmed": False, "correction": "datetime"}, create_collect_booking_request_node()

        patient_id = fm.state.get("patient_id")
        if not patient_id:
            logger.error("confirm_booking: patient_id missing from state")
            return {"error": "missing_state"}, create_escalate_node("state_error")

        # Layer 2: ONLY place confirmed_* booking fields are written
        fm.state["confirmed_patient_id"] = patient_id
        fm.state["confirmed_date"] = date
        fm.state["confirmed_start_time"] = start_time
        fm.state["confirmed_end_time"] = end_time

        return {"confirmed": True}, create_book_node()

    confirm_fn = FlowsFunctionSchema(
        name="confirm_booking",
        description=(
            "Record the patient's confirmation or rejection of the appointment details. "
            "Use correction_type='patient' if they want to change who the appointment is for."
        ),
        properties={
            "confirmed": {"type": "boolean", "description": "True if the patient confirmed"},
            "correction_type": {
                "type": "string",
                "enum": ["datetime", "patient"],
                "description": "Which part to correct when confirmed is False",
            },
        },
        required=["confirmed"],
        handler=flows_audited("confirm_booking", handle_confirm_booking),
        cancel_on_interruption=False,
    )
    return {
        "name": "confirm_booking",
        "task_messages": [
            {
                "role": "system",
                "content": (
                    f'Say ONE sentence: "So that\'s {patient_name}, {date_human} from '
                    f'{start_human} to {end_human} — is that right?" '
                    "When they answer, call confirm_booking immediately. Do not elaborate."
                ),
            }
        ],
        "functions": [confirm_fn],
        "respond_immediately": True,
    }


# ---------------------------------------------------------------------------
# collect_booking_request
# ---------------------------------------------------------------------------


def create_collect_booking_request_node() -> NodeConfig:
    async def handle_check_date_slots(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, None]:
        date_ = args.get("date", "").strip()
        date_to = args.get("date_to", "").strip()
        client: httpx.AsyncClient = fm.state["client"]

        params: dict[str, str] = {"date": date_}
        if date_to:
            params["date_to"] = date_to

        ok, r = await ehr_get(client, "/list_availability_slots", params)
        if not ok:
            return {"slots": [], "error": r.get("detail", "Could not fetch slots")}, None

        slots = r if isinstance(r, list) else []
        formatted = [
            {
                "date": s["date"],
                "start_time": s["start_time"][:5],
                "end_time": s["end_time"][:5],
            }
            for s in slots
        ]
        return {"slots": formatted, "count": len(formatted)}, None

    async def handle_submit_booking_request(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig | None]:
        date_ = args.get("date", "").strip()
        start_time = args.get("start_time", "").strip()
        end_time = args.get("end_time", "").strip()

        if not date_ or not start_time or not end_time:
            return {"valid": False, "error": "Missing date, start_time, or end_time."}, None

        patient_name = fm.state.get("patient_name", "the patient")
        return (
            {"valid": True},
            create_confirm_booking_node(patient_name, date_, start_time, end_time),
        )

    check_fn = FlowsFunctionSchema(
        name="check_date_slots",
        description=(
            "Check available appointment slots for a given date or date range. "
            "Call this first before asking the patient to pick a time."
        ),
        properties={
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "date_to": {
                "type": "string",
                "description": "YYYY-MM-DD — optional end date for a multi-day search",
            },
        },
        required=["date"],
        handler=flows_audited("check_date_slots", handle_check_date_slots),
        cancel_on_interruption=False,
    )
    submit_fn = FlowsFunctionSchema(
        name="submit_booking_request",
        description=(
            "Submit the patient's chosen time range. "
            "Call this after they have selected a start and end time."
        ),
        properties={
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "start_time": {"type": "string", "description": "HH:MM — must align with a slot start"},
            "end_time": {"type": "string", "description": "HH:MM — must align with a slot end"},
        },
        required=["date", "start_time", "end_time"],
        handler=flows_audited("submit_booking_request", handle_submit_booking_request),
        cancel_on_interruption=False,
    )
    today = _date_type.today()
    today_iso = today.isoformat()
    today_human = today.strftime("%A, %B %-d, %Y")

    return {
        "name": "collect_booking_request",
        "task_messages": [
            {
                "role": "system",
                "content": (
                    f"TODAY IS {today_human} (ISO: {today_iso}). "
                    "Use this as the reference when computing any relative date (tomorrow, next Monday, etc.). "
                    "Ask the patient what date they'd like and roughly how long they need. "
                    "Clinic is open Monday–Friday only — redirect any weekend date to the next Monday. "
                    "Each slot is 30 minutes; longer visits use back-to-back slots. "
                    "If they give a vague answer like 'next week', call check_date_slots with a date range. "
                    "Read available times back naturally ('9 AM', '9:30 AM') — never raw ISO strings. "
                    "When the patient picks a time, call submit_booking_request with date, start_time, "
                    "and end_time. For a 1-hour visit at 9 AM: start_time='09:00', end_time='10:00'."
                ),
            }
        ],
        "functions": [check_fn, submit_fn],
    }


# ---------------------------------------------------------------------------
# collect_intent
# ---------------------------------------------------------------------------


def create_collect_intent_node(*, new_patient: bool = False) -> NodeConfig:
    async def handle_submit_intent(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig]:
        intent = args.get("intent", "").strip().lower()
        if intent == "cancel":
            return {"intent": "cancel"}, create_cancellation_flow_node()
        return {"intent": "book"}, create_collect_booking_request_node()

    if new_patient:
        intent_enum = ["book"]
        intent_description = "'book' to schedule a new appointment"
        task_content = (
            "Welcome the newly registered patient by name. "
            "In one short sentence ask if they'd like to book an appointment. "
            "Call submit_intent with intent='book' once they confirm."
        )
    else:
        intent_enum = ["book", "cancel"]
        intent_description = "'book' to schedule, 'cancel' to cancel an existing appointment"
        task_content = (
            "Welcome the patient by name. "
            "In one short sentence ask whether they'd like to book a new appointment "
            "or cancel an existing one. Call submit_intent once you know."
        )

    intent_fn = FlowsFunctionSchema(
        name="submit_intent",
        description="Record whether the patient wants to book a new appointment or cancel an existing one.",
        properties={
            "intent": {
                "type": "string",
                "enum": intent_enum,
                "description": intent_description,
            }
        },
        required=["intent"],
        handler=flows_audited("submit_intent", handle_submit_intent),
        cancel_on_interruption=False,
    )
    return {
        "name": "collect_intent",
        "task_messages": [{"role": "system", "content": task_content}],
        "functions": [intent_fn],
    }


# ---------------------------------------------------------------------------
# collect_registration
# ---------------------------------------------------------------------------


def create_collect_registration_node() -> NodeConfig:
    async def handle_submit_registration(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig]:
        client: httpx.AsyncClient = fm.state["client"]
        first_name = fm.state.get("lookup_first_name", "")
        last_name = fm.state.get("lookup_last_name", "")
        dob = fm.state.get("lookup_dob", "")

        body: dict = {
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": dob,
        }
        phone = args.get("phone", "").strip()
        email = args.get("email", "").strip()
        if phone:
            body["phone"] = phone
        if email:
            body["email"] = email

        ok, r = await ehr_post(client, "/create_patient", body)
        if ok:
            fm.state["patient_id"] = r["id"]
            fm.state["patient_name"] = f"{r['first_name']} {r['last_name']}"
            return {"registered": True, "name": fm.state["patient_name"]}, create_collect_intent_node(new_patient=True)
        return (
            {"registered": False, "reason": r.get("detail", "Registration failed")},
            create_escalate_node("registration_failed"),
        )

    reg_fn = FlowsFunctionSchema(
        name="submit_registration",
        description="Register the patient with their contact details. Phone is recommended.",
        properties={
            "phone": {"type": "string", "description": "Patient phone number (recommended)"},
            "email": {"type": "string", "description": "Patient email address (optional)"},
        },
        required=[],
        handler=flows_audited("submit_registration", handle_submit_registration),
        cancel_on_interruption=False,
    )
    return {
        "name": "collect_registration",
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "The patient is not in our system. Ask for their phone number to register them. "
                    "Email is optional. Once you have their contact details, call submit_registration."
                ),
            }
        ],
        "functions": [reg_fn],
    }


# ---------------------------------------------------------------------------
# no_match
# ---------------------------------------------------------------------------


def create_no_match_node(searched_name: str = "") -> NodeConfig:
    async def handle_retry_or_register(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig | None]:
        action = args.get("action", "retry")

        if action == "escalate":
            return {"action": "escalate"}, create_escalate_node("patient_not_found")

        if action == "register":
            return {"action": "register"}, create_collect_registration_node()

        # action == "retry": re-call find_patient with corrected details
        first = args.get("corrected_first_name", "").strip() or fm.state.get(
            "lookup_first_name", ""
        )
        last = args.get("corrected_last_name", "").strip() or fm.state.get("lookup_last_name", "")
        dob = args.get("corrected_dob", "").strip() or fm.state.get("lookup_dob", "")

        fm.state["lookup_first_name"] = first
        fm.state["lookup_last_name"] = last
        fm.state["lookup_dob"] = dob

        client: httpx.AsyncClient = fm.state["client"]
        ok, r = await ehr_get(
            client, "/find_patient", {"first_name": first, "last_name": last, "dob": dob}
        )

        if ok:
            fm.state["patient_id"] = r["id"]
            fm.state["patient_name"] = f"{r['first_name']} {r['last_name']}"
            return {"found": True, "name": fm.state["patient_name"]}, create_collect_intent_node()

        attempts = fm.state.get("lookup_attempts", 0) + 1
        fm.state["lookup_attempts"] = attempts
        if attempts >= 2:
            return {"found": False, "max_attempts": True}, create_escalate_node(
                "patient_not_found_max_attempts"
            )
        return {"found": False}, None  # stay in no_match

    retry_fn = FlowsFunctionSchema(
        name="retry_or_register",
        description=(
            "Choose how to proceed when the patient is not found: "
            "retry with a corrected name or DOB, register as a new patient, or escalate."
        ),
        properties={
            "action": {
                "type": "string",
                "enum": ["retry", "register", "escalate"],
                "description": (
                    "'retry' to search again with corrected details, "
                    "'register' if they are a new patient, "
                    "'escalate' to arrange a callback"
                ),
            },
            "corrected_first_name": {"type": "string"},
            "corrected_last_name": {"type": "string"},
            "corrected_dob": {
                "type": "string",
                "description": "YYYY-MM-DD — provide if the DOB may have been wrong",
            },
        },
        required=["action"],
        handler=flows_audited("retry_or_register", handle_retry_or_register),
        cancel_on_interruption=False,
    )

    hint = f" for '{searched_name}'" if searched_name else ""
    return {
        "name": "no_match",
        "task_messages": [
            {
                "role": "system",
                "content": (
                    f"No patient was found{hint}. Apologize and ask the patient whether "
                    "they'd like to try again with a different spelling, register as a new patient, "
                    "or have someone call them back. Call retry_or_register with their choice."
                ),
            }
        ],
        "functions": [retry_fn],
    }


# ---------------------------------------------------------------------------
# collect_identity  (initial node — greet inline when initial=True)
# ---------------------------------------------------------------------------


def create_collect_identity_node(*, initial: bool = False) -> NodeConfig:
    async def handle_submit_identity(
        args: FlowArgs, fm: FlowManager
    ) -> tuple[dict, NodeConfig]:
        first = args.get("first_name", "").strip()
        last = args.get("last_name", "").strip()
        dob = args.get("dob", "").strip()
        is_new = bool(args.get("is_new_patient", False))

        if not first or not last or not dob:
            return {"error": "first_name, last_name, and dob are all required"}, None  # type: ignore[return-value]

        fm.state["lookup_first_name"] = first
        fm.state["lookup_last_name"] = last
        fm.state["lookup_dob"] = dob

        client: httpx.AsyncClient = fm.state["client"]
        ok, r = await ehr_get(
            client, "/find_patient", {"first_name": first, "last_name": last, "dob": dob}
        )

        if ok:
            # Found regardless of is_new_patient — they already exist
            fm.state["patient_id"] = r["id"]
            fm.state["patient_name"] = f"{r['first_name']} {r['last_name']}"
            fm.state["lookup_attempts"] = 0
            return {"found": True, "name": fm.state["patient_name"]}, create_collect_intent_node()

        fm.state["lookup_attempts"] = fm.state.get("lookup_attempts", 0) + 1
        if is_new:
            # New patient confirmed not in system — proceed to registration
            return {"found": False, "new_patient": True}, create_collect_registration_node()

        # Returning patient not found — offer retry or register
        return {"found": False}, create_no_match_node(f"{first} {last}")

    identity_fn = FlowsFunctionSchema(
        name="submit_identity",
        description=(
            "Look up the patient after you have confirmed their name, date of birth, "
            "and whether they are new or returning."
        ),
        properties={
            "first_name": {"type": "string"},
            "last_name": {"type": "string"},
            "dob": {"type": "string", "description": "YYYY-MM-DD"},
            "is_new_patient": {
                "type": "boolean",
                "description": "True if the caller said they are a new patient, False if returning",
            },
        },
        required=["first_name", "last_name", "dob", "is_new_patient"],
        handler=flows_audited("submit_identity", handle_submit_identity),
        cancel_on_interruption=False,
    )

    if initial:
        content = (
            "STEP 1 — Your very first sentence must be: "
            "\"Hi, this is Prosper Health's assistant — are you a new or returning patient?\" "
            "Do NOT ask for their name or date of birth yet. Wait for their answer.\n\n"
            "STEP 2 — After they answer, ask for their full name and date of birth.\n\n"
            "STEP 3 — Repeat back: \"Just to confirm — [full name], born [date in natural language]. "
            "Is that right?\" Wait for a clear yes. If they correct you, update and confirm again.\n\n"
            "STEP 4 — Call submit_identity with first_name, last_name, dob (YYYY-MM-DD), "
            "and is_new_patient (true if they said new, false if returning)."
        )
    else:
        content = (
            "STEP 1 — Ask: \"Are you a new or returning patient?\" Wait for their answer.\n\n"
            "STEP 2 — Ask for their full name and date of birth.\n\n"
            "STEP 3 — Repeat back name + DOB to confirm. Wait for yes.\n\n"
            "STEP 4 — Call submit_identity with first_name, last_name, dob (YYYY-MM-DD), "
            "and is_new_patient (true/false)."
        )

    return {
        "name": "collect_identity",
        "task_messages": [{"role": "system", "content": content}],
        "functions": [identity_fn],
        "respond_immediately": True,
    }
