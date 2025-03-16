import re
import subprocess
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

RECRUITER_EMAIL = "bvsuyameendra@gmail.com"
CANDIDATE_EMAIL = "manchemvishnusrikar@gmail.com"
TIME_ZONE = "Asia/Kolkata"

def run_ollama_model(query):
    """Runs llama3 model with Ollama, capturing output in UTF-8."""
    command = ["ollama", "run", "llama3", query]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    return result.stdout.strip()

def get_now_ist() -> datetime:
    """
    Returns current IST time as a naive datetime.
    If your system clock is local IST, just use datetime.now().
    Otherwise, do UTC + 5:30.
    """
    now_utc = datetime.utcnow()
    return now_utc + timedelta(hours=5, minutes=30)

def to_utc(ist_dt: datetime) -> datetime:
    """Convert naive IST datetime to UTC (IST=UTC+5:30)."""
    return ist_dt - timedelta(hours=5, minutes=30)

def get_busy_slots(service, email, start_ist: datetime, end_ist: datetime):
    """Fetch busy slots for 'email' between [start_ist, end_ist) in IST, converting to UTC for the Calendar API."""
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

def is_slot_free_for_both(service, recruiter, candidate, start_ist: datetime, end_ist: datetime):
    """Check if both recruiter & candidate are free in [start_ist, end_ist) IST."""
    recruiter_busy = get_busy_slots(service, recruiter, start_ist, end_ist)
    candidate_busy = get_busy_slots(service, candidate, start_ist, end_ist)
    return (not recruiter_busy) and (not candidate_busy)

def clamp_to_working_hours(ist_dt: datetime) -> datetime:
    """Clamps 'ist_dt' to Mon–Fri, 9 AM–7 PM in IST."""
    while ist_dt.weekday() >= 5:  # Sat=5, Sun=6
        ist_dt += timedelta(days=1)
        ist_dt = ist_dt.replace(hour=9, minute=0, second=0, microsecond=0)

    if ist_dt.hour < 9:
        ist_dt = ist_dt.replace(hour=9, minute=0, second=0, microsecond=0)

    elif ist_dt.hour >= 19:
        ist_dt += timedelta(days=1)
        while ist_dt.weekday() >= 5:
            ist_dt += timedelta(days=1)
        ist_dt = ist_dt.replace(hour=9, minute=0, second=0, microsecond=0)

    return ist_dt

def clamp_to_future_2025(ist_dt: datetime) -> datetime:
    """
    Ensures:
      1) Year >= 2025
      2) The day/month is not before "today" in 2025 if we're already beyond that day.

    Example: If today is effectively 2025-03-17 in real time, and the AI picks 2025-03-13,
    we shift it to 2025-03-17 (today).
    """
    now_ist = get_now_ist()

    if ist_dt.year < 2025:
        ist_dt = ist_dt.replace(year=2025)


    real_now = now_ist 
    virtual_2025 = datetime(
        2025,
        real_now.month,
        real_now.day,
        real_now.hour,
        real_now.minute,
        real_now.second,
        real_now.microsecond
    )

    if ist_dt < virtual_2025:
        ist_dt = virtual_2025

    return ist_dt

def find_first_free_slot(service, start_ist: datetime) -> datetime:
    """
    Searches forward hour by hour from 'start_ist' in IST,
    clamping each iteration to Mon–Fri, 9–19 IST,
    until it finds a free 1-hour slot for both participants.
    """
    current = start_ist
    max_attempts = 3000
    attempts = 0

    while attempts < max_attempts:
        current = clamp_to_future_2025(current)
        current = clamp_to_working_hours(current)
        end_current = current + timedelta(hours=1)

        if is_slot_free_for_both(service, RECRUITER_EMAIL, CANDIDATE_EMAIL, current, end_current):
            return current
        else:
            current += timedelta(hours=1)
            attempts += 1

    return None

def main():
    creds = Credentials.from_authorized_user_file("token.json")
    service = build("calendar", "v3", credentials=creds)

    prompt = f"""
Find an available 1-hour slot (Monday to Friday only, 9 AM to 7 PM IST) 
for an interview between:
- Recruiter ({RECRUITER_EMAIL})
- Candidate ({CANDIDATE_EMAIL})

Output exactly one line in ISO 8601 format (YYYY-MM-DDTHH:MM:SS) with no timezone.
Do not include +05:30 or any text other than the date/time.
"""

    response_text = run_ollama_model(prompt)
    print(f"AI Raw Response:\n{response_text}\n")

    match_time = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", response_text)
    if not match_time:
        raise ValueError(f"Could not extract valid datetime from AI response:\n{response_text}")
    ai_time_str = match_time.group(1)
    ai_time_ist = datetime.strptime(ai_time_str, "%Y-%m-%dT%H:%M:%S")

    print(f"AI-Suggested IST: {ai_time_ist} (Year={ai_time_ist.year})")

    free_slot_ist = find_first_free_slot(service, ai_time_ist)
    if not free_slot_ist:
        raise ValueError("No free slot found in the search range.")

    event_start_ist = free_slot_ist
    event_end_ist = free_slot_ist + timedelta(hours=1)

    start_str = event_start_ist.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"
    end_str = event_end_ist.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"

    event = {
        "summary": "AI-Scheduled Interview",
        "location": "Google Meet",
        "description": "Scheduled in IST, never picking a day behind today's date in 2025.",
        "start": {"dateTime": start_str, "timeZone": TIME_ZONE},
        "end": {"dateTime": end_str, "timeZone": TIME_ZONE},
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

    print("AI-Scheduled Interview (IST)!")
    print(f"Final Chosen IST Slot: {free_slot_ist.strftime('%Y-%m-%d %I:%M %p')} (Year={free_slot_ist.year})")
    print(f"Event Link: {event_response.get('htmlLink')}")
    print(f"Google Meet Link: {event_response['conferenceData']['entryPoints'][0]['uri']}")
    print("\nWe clamp each iteration to a day >= 'today' in 2025, so it never picks a date behind the real 'today' date.")

if __name__ == "__main__":
    main()
