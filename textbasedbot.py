import re
import subprocess
import json
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

RECRUITER_EMAIL = "bvsuyameendra@gmail.com"
CANDIDATE_EMAIL = "manchemvishnusrikar@gmail.com"
TIME_ZONE = "Asia/Kolkata"

def run_ollama_model(query: str) -> str:
    """
    Runs llama3 model with Ollama, capturing output in UTF-8.
    """
    command = ["ollama", "run", "llama3", query]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    return result.stdout.strip()

def parse_candidate_availability(natural_text: str):
    """
    Asks LLaMA to convert candidate's text (e.g. 
    'I'm free next Monday between 2 PM and 4 PM')
    into a JSON with 'start' and 'end' in ISO 8601.

    Example output:
    {
      "start": "2025-03-24T14:00:00",
      "end":   "2025-03-24T16:00:00"
    }
    """
    prompt = f"""
You are a date/time parser. Convert the following availability description 
into JSON with "start" and "end" in ISO8601 format (YYYY-MM-DDTHH:MM:SS), 
assuming the user is referring to the next occurrence of that day/time in the future.

Input: {natural_text}

Output only JSON, e.g.:
{{ "start": "2025-03-24T14:00:00", "end": "2025-03-24T16:00:00" }}
No extra text.
"""
    response = run_ollama_model(prompt)
    try:
        match = re.search(r"(\{.*\})", response, flags=re.DOTALL)
        if not match:
            raise ValueError(f"Could not find JSON in LLM response:\n{response}")
        json_str = match.group(1)
        availability = json.loads(json_str)
        return availability
    except Exception as e:
        raise ValueError(f"Failed to parse JSON from LLM:\n{response}\nError: {e}")

def to_utc(ist_dt: datetime) -> datetime:
    """Convert naive IST datetime to UTC (IST=UTC+5:30)."""
    return ist_dt - timedelta(hours=5, minutes=30)

def get_busy_slots(service, email, start_ist: datetime, end_ist: datetime):
    """Fetch busy slots for 'email' in [start_ist, end_ist) IST, converting to UTC for API."""
    start_utc = to_utc(start_ist)
    end_utc = to_utc(end_ist)
    body = {
        "timeMin": start_utc.isoformat() + "Z",
        "timeMax": end_utc.isoformat() + "Z",
        "timeZone": "UTC",
        "items": [{"id": email}],
    }
    response = service.freebusy().query(body=body).execute()
    return response["calendars"][email]["busy"]

def is_slot_free_for_both(service, recruiter, candidate, start_ist, end_ist):
    """Check if both are free in [start_ist, end_ist) IST."""
    r_busy = get_busy_slots(service, recruiter, start_ist, end_ist)
    c_busy = get_busy_slots(service, candidate, start_ist, end_ist)
    return (not r_busy) and (not c_busy)

def find_1hr_slot_within_range(service, candidate_start, candidate_end):
    """
    The candidate is free in [candidate_start, candidate_end).
    We check each hour in that range to see if the recruiter is also free.
    Return the first free 1-hour block (start, end) or None if none found.
    """
    current = candidate_start.replace(minute=0, second=0, microsecond=0)
    if current < candidate_start:
        current += timedelta(hours=1)

    while current + timedelta(hours=1) <= candidate_end:
        slot_start = current
        slot_end = current + timedelta(hours=1)
        if is_slot_free_for_both(service, RECRUITER_EMAIL, CANDIDATE_EMAIL, slot_start, slot_end):
            return (slot_start, slot_end)
        current += timedelta(hours=1)

    return None

def create_calendar_event(service, slot_start_ist, slot_end_ist):
    """Create a Google Calendar event for the chosen slot in IST."""
    start_str = slot_start_ist.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"
    end_str   = slot_end_ist.strftime("%Y-%m-%dT%H:%M:%S")   + "+05:30"

    event = {
        "summary": "AI-Scheduled Interview",
        "location": "Google Meet",
        "description": "Scheduled based on candidate's stated availability and recruiter's free time.",
        "start": {"dateTime": start_str, "timeZone": TIME_ZONE},
        "end":   {"dateTime": end_str,   "timeZone": TIME_ZONE},
        "attendees": [
            {"email": RECRUITER_EMAIL},
            {"email": CANDIDATE_EMAIL}
        ],
        "conferenceData": {
            "createRequest": {"requestId": "meeting-request"}
        },
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "email", "minutes": 30}]
        },
    }

    event_response = service.events().insert(
        calendarId="primary",
        body=event,
        conferenceDataVersion=1
    ).execute()
    return event_response

def main():
    candidate_text = input("Candidate Availability (e.g. 'I'm free next Monday between 2 PM and 4 PM'): ")

    parsed = parse_candidate_availability(candidate_text)
    candidate_start_ist = datetime.strptime(parsed["start"], "%Y-%m-%dT%H:%M:%S")
    candidate_end_ist   = datetime.strptime(parsed["end"],   "%Y-%m-%dT%H:%M:%S")

    creds = Credentials.from_authorized_user_file("token.json")
    service = build("calendar", "v3", credentials=creds)

    slot = find_1hr_slot_within_range(service, candidate_start_ist, candidate_end_ist)
    if not slot:
        print("No free 1-hour slot found that matches both candidate and recruiter availability.")
        return
    slot_start, slot_end = slot
    print(f"Chosen Slot: {slot_start} to {slot_end} IST")

    event_response = create_calendar_event(service, slot_start, slot_end)

    print("\n Meeting Scheduled!")
    print(f"Event Link: {event_response.get('htmlLink')}")
    meet_link = event_response.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri")
    print(f"Google Meet Link: {meet_link}")

if __name__ == "__main__":
    main()
