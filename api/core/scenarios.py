"""Built-in simulation scenarios

  1. new_patient_books     Alice registers (new) and books tomorrow 09:00.
  2. existing_patient_cancels  Alice (now returning) cancels that 09:00 appointment.
  3. misspelled_name_retry Alice (returning) books tomorrow 14:00, but first gives a
                           wrong spelling so the bot has to retry the lookup.
  4. weekend_redirect      Alice tries to book a Saturday and is redirected to Monday.
"""

from schemas.simulation import ExpectedDB, Scenario, ScenarioSummary

_PATIENT = "Alice Smith"
_DOB = "1991-03-15"

SCENARIOS: dict[str, Scenario] = {
    "new_patient_books": Scenario(
        id="new_patient_books",
        name="1. New Patient Books",
        description="A new patient registers and books a 30-minute appointment for tomorrow at 9 AM.",
        persona=(
            "You are Alice Smith, born 1991-03-15. You speak clearly and concisely. "
            "You have never been to this clinic before — you are a NEW patient. "
            "You want to book an appointment for tomorrow morning."
        ),
        goal="Register as a new patient and book a 30-minute appointment for tomorrow at 9:00 AM.",
        expected_db=ExpectedDB(
            patient_name=_PATIENT,
            patient_dob=_DOB,
            appointment_date="tomorrow",
            appointment_start="09:00",
            appointment_end="09:30",
        ),
        rubric=[
            "The bot asked whether the caller was new or returning before proceeding.",
            "The bot confirmed the patient's name and date of birth before looking them up.",
            "When the patient was not found, the bot offered registration.",
            "The bot collected a phone number during registration.",
            "The bot asked for the date and time preference.",
            "The bot confirmed the appointment details before booking.",
            "The bot never exposed UUIDs or internal IDs aloud.",
        ],
    ),
    "existing_patient_cancels": Scenario(
        id="existing_patient_cancels",
        name="2. Existing Patient Cancels",
        description="The patient from scenario 1 calls back to cancel their 9 AM appointment.",
        persona=(
            "You are Alice Smith, born 1991-03-15. You are a RETURNING patient. "
            "You booked an appointment for tomorrow at 9:00 AM and now need to cancel it. "
            "You speak directly and clearly."
        ),
        goal="Cancel the appointment scheduled for tomorrow at 9:00 AM.",
        expected_db=ExpectedDB(
            patient_name=_PATIENT,
            patient_dob=_DOB,
            appointment_date="tomorrow",
            appointment_start="09:00",
            appointment_end="09:30",
            # The tomorrow-9:00 appointment must no longer be scheduled.
            appointment_scheduled=False,
        ),
        rubric=[
            "The bot identified the patient by name and date of birth.",
            "The bot asked whether to book or cancel.",
            "The bot listed the patient's appointments before allowing cancellation.",
            "The bot confirmed which appointment to cancel by date and time (not by UUID).",
            "The appointment was successfully cancelled.",
        ],
    ),
    "misspelled_name_retry": Scenario(
        id="misspelled_name_retry",
        name="3. Misspelled Name Retry",
        description="The returning patient gives a wrong spelling first; the bot retries and finds them.",
        persona=(
            "You are Alice Smith, born 1991-03-15. You are a RETURNING patient. "
            "When the assistant asks for your last name, FIRST say it is spelled "
            "'S-M-Y-T-H'. When the assistant says it can't find you, correct it to "
            "the right spelling: 'S-M-I-T-H'. You want to book an appointment for "
            "tomorrow at 2 PM."
        ),
        goal="Book an appointment for tomorrow at 14:00 (2:00 PM), correcting your name spelling when needed.",
        expected_db=ExpectedDB(
            patient_name=_PATIENT,
            patient_dob=_DOB,
            appointment_date="tomorrow",
            appointment_start="14:00",
            appointment_end="14:30",
        ),
        rubric=[
            "The bot attempted to find the patient with the first (wrong) spelling.",
            "When not found, the bot asked the patient to confirm or re-spell their name.",
            "The bot retried the lookup with the corrected spelling.",
            "The bot found the patient on the retry.",
            "The bot proceeded to book the appointment.",
        ],
    ),
    "weekend_redirect": Scenario(
        id="weekend_redirect",
        name="4. Weekend Redirect",
        description="The patient asks for a Saturday appointment and the bot redirects to the next Monday.",
        persona=(
            "You are Alice Smith, born 1991-03-15. You are a RETURNING patient. "
            "You want to book an appointment for this Saturday. You are flexible and "
            "will accept Monday if Saturday isn't available."
        ),
        goal="Try to book an appointment for this Saturday; accept the next Monday at 9 AM if redirected.",
        expected_db=ExpectedDB(
            patient_name=_PATIENT,
            patient_dob=_DOB,
            appointment_date="next_monday",
            appointment_start="09:00",
            appointment_end="09:30",
        ),
        rubric=[
            "The bot informed the caller that the clinic is only open Monday–Friday.",
            "The bot suggested the next Monday (or another weekday).",
            "The bot did not book a Saturday appointment.",
        ],
    ),
}


def get_scenario(scenario_id: str) -> Scenario | None:
    return SCENARIOS.get(scenario_id)


def list_scenarios() -> list[ScenarioSummary]:
    return [
        ScenarioSummary(id=s.id, name=s.name, description=s.description)
        for s in SCENARIOS.values()
    ]
