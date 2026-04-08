import os
import base64
import json
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "google_credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "google_token.json")


def get_google_services():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Google credentials not found. Please place your OAuth2 credentials at: {CREDENTIALS_FILE}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)
    return gmail, calendar


SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")


class GoogleAgent:
    def __init__(self):
        self._gmail = None
        self._calendar = None

    def _get_timezone(self) -> str:
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                return json.load(f).get("timezone", "Europe/Paris")
        except Exception:
            return "Europe/Paris"

    def _ensure_connected(self):
        if not self._gmail or not self._calendar:
            self._gmail, self._calendar = get_google_services()

    # ─── GMAIL ───────────────────────────────────────────────────────────────

    def read_emails(self, max_results=5, query="in:inbox"):
        self._ensure_connected()
        results = self._gmail.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = results.get("messages", [])
        if not messages:
            return "No emails found."

        output = []
        for msg in messages:
            m = self._gmail.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in m["payload"]["headers"]}
            snippet = m.get("snippet", "")[:150]
            output.append(
                f"From: {headers.get('From', '?')}\n"
                f"Subject: {headers.get('Subject', '?')}\n"
                f"Date: {headers.get('Date', '?')}\n"
                f"Preview: {snippet}"
            )
        return "\n\n".join(output)

    def send_email(self, to: str, subject: str, body: str):
        self._ensure_connected()
        msg = MIMEMultipart()
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self._gmail.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return f"Email sent to {to} with subject '{subject}'."

    def search_emails(self, query: str, max_results=5):
        return self.read_emails(max_results=max_results, query=query)

    def get_email_body(self, message_id: str):
        self._ensure_connected()
        m = self._gmail.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        payload = m.get("payload", {})

        def extract_body(part):
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            for sub in part.get("parts", []):
                result = extract_body(sub)
                if result:
                    return result
            return ""

        body = extract_body(payload)
        return body[:2000] if body else "(no readable body)"

    # ─── CALENDAR ────────────────────────────────────────────────────────────

    def list_events(self, max_results=10, time_min=None):
        self._ensure_connected()
        if not time_min:
            time_min = datetime.now(timezone.utc).isoformat()
        events_result = self._calendar.events().list(
            calendarId="primary",
            timeMin=time_min,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return "No upcoming events found."

        output = []
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", "?"))
            output.append(f"- {e.get('summary', 'No title')} | {start}")
        return "\n".join(output)

    def create_event(self, title: str, start: str, end: str, description: str = "", attendees: list = None):
        self._ensure_connected()
        tz = self._get_timezone()
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start, "timeZone": tz},
            "end": {"dateTime": end, "timeZone": tz},
        }
        if attendees:
            event["attendees"] = [{"email": a} for a in attendees]
        created = self._calendar.events().insert(
            calendarId="primary", body=event
        ).execute()
        return f"Event '{title}' created on {start}. Link: {created.get('htmlLink', '')}"

    def delete_event(self, event_id: str):
        self._ensure_connected()
        self._calendar.events().delete(
            calendarId="primary", eventId=event_id
        ).execute()
        return f"Event {event_id} deleted."

    def find_event(self, query: str, max_results=5):
        self._ensure_connected()
        time_min = datetime.now(timezone.utc).isoformat()
        events_result = self._calendar.events().list(
            calendarId="primary",
            timeMin=time_min,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
            q=query
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return f"No events found matching '{query}'."
        output = []
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", "?"))
            output.append(f"ID: {e['id']} | {e.get('summary', 'No title')} | {start}")
        return "\n".join(output)
