from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

creds = Credentials.from_authorized_user_file("token.json")

service = build("calendar", "v3", credentials=creds)

event = {
    "summary": "Interview with Mohammed Aasif",
    "location": "Google Meet Link",
    "description": "AI-scheduled interview",
    "start": {"dateTime": "2025-03-16T15:00:00", "timeZone": "Asia/Kolkata"},
    "end": {"dateTime": "2025-03-16T16:00:00", "timeZone": "Asia/Kolkata"},
    "attendees": [{"email": "bvsuyameendra@gmail.com"}, {"email": "manchemvishnusrikar@gmail.com"}],
    "reminders": {"useDefault": False, "overrides": [{"method": "email", "minutes": 30}]},
}

event_response = service.events().insert(calendarId="primary", body=event).execute()

print("Interview Scheduled!")
print(f"Event Link: {event_response.get('htmlLink')}")
