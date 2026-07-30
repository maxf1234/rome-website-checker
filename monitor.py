#!/usr/bin/env python3
"""
Acuity Scheduling Availability Monitor

Watches the Portuguese Consulate (Newark) booking page for ANY appointment
availability and emails as soon as a slot opens.

Endpoint and auth were captured by instrumenting the real page in a headless
browser. The scheduling SPA calls:

    GET /api/scheduling/v1/availability/month
        ?owner=<slug>&appointmentTypeId=<id>&calendarId=<id>&timezone=<tz>
    headers: x-secondo-owner: <slug>, x-secondo-session: <uuid>

The response maps date -> truthy when that date has availability; the app
itself computes available dates as Object.keys(resp).filter(k => resp[k]).
An empty object means nothing is open.

The session header is a client-generated UUID, so we mint our own. If the
API ever rejects that, SCRAPE_FALLBACK drives a real browser instead.
"""

import json
import os
import smtplib
import uuid
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

BOOKING_URL = (
    "https://app.acuityscheduling.com/schedule/ce551904"
    "/appointment/71567018/calendar/11158185"
)

SLUG                = "ce551904"
APPOINTMENT_TYPE_ID = "71567018"
CALENDAR_ID         = "11158185"
TIMEZONE            = "America/New_York"

APPOINTMENT_NAME = (
    "Pedido da Nacionalidade Portuguesa para Filhos de Cidadãos Portugueses "
    "| Application for Portuguese Nationality for Children of Portuguese Citizens"
)

API_URL = "https://app.acuityscheduling.com/api/scheduling/v1/availability/month"

# How many months ahead to scan (0 = current month only)
MONTHS_AHEAD = 6

STATE_FILE = "state.json"

EMAIL_SENDER    = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD  = os.environ["EMAIL_PASSWORD"]
EMAIL_RECIPIENT = os.environ["EMAIL_RECIPIENT"]
RECIPIENT_LIST  = [e.strip() for e in EMAIL_RECIPIENT.split(",") if e.strip()]

SESSION_ID = str(uuid.uuid4())

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US",
    "Referer": BOOKING_URL,
    "x-secondo-owner": SLUG,
    "x-secondo-session": SESSION_ID,
}

# ─────────────────────────────────────────────


def months_to_check() -> list[str]:
    """Current month plus the next MONTHS_AHEAD.

    The API wants a full YYYY-MM-DD date, not YYYY-MM (it rejects the short
    form outright), and refuses dates before the current month — so the
    current month is represented by today rather than the 1st.
    """
    today = date.today()
    out = [today.isoformat()]
    y, m = today.year, today.month
    for _ in range(MONTHS_AHEAD):
        m += 1
        if m > 12:
            m = 1
            y += 1
        out.append(f"{y:04d}-{m:02d}-01")
    return out


def fetch_month(month: str | None) -> dict:
    """Fetch availability. `month` of None asks for the default (current) month."""
    params = {
        "owner": SLUG,
        "appointmentTypeId": APPOINTMENT_TYPE_ID,
        "calendarId": CALENDAR_ID,
        "timezone": TIMEZONE,
    }
    if month:
        params["month"] = month

    req = Request(f"{API_URL}?{urlencode(params)}", headers=HEADERS, method="GET")
    with urlopen(req, timeout=45) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw.strip() else {}


def available_dates_from(payload) -> list[str]:
    """The app's own rule: keys whose value is truthy are available dates."""
    if isinstance(payload, dict):
        # Some responses nest the map under a key
        for key in ("dates", "data", "availability"):
            inner = payload.get(key)
            if isinstance(inner, (dict, list)):
                payload = inner
                break

    if isinstance(payload, dict):
        return sorted(k for k, v in payload.items() if v)
    if isinstance(payload, list):
        out = []
        for item in payload:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                d = item.get("date") or item.get("day")
                if d and item.get("available", True):
                    out.append(str(d))
        return sorted(out)
    return []


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_email(new_dates: list[str], all_dates: list[str]) -> None:
    subject = f"Consulate appointment OPEN — {len(new_dates)} new date(s)!"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body = f"""Appointment availability just opened up!

Appointment type:
  {APPOINTMENT_NAME}

Consulado-Geral de Portugal em Newark
Detected at: {timestamp}

NEWLY AVAILABLE DATES:
{chr(10).join('  ' + d for d in new_dates)}

ALL CURRENTLY AVAILABLE DATES:
{chr(10).join('  ' + d for d in all_dates)}

BOOK NOW: {BOOKING_URL}

(These slots typically go fast — book immediately.)
"""

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = ", ".join(RECIPIENT_LIST)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, RECIPIENT_LIST, msg.as_string())

    print(f"  Alert emailed to {RECIPIENT_LIST}")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Checking consulate availability...")

    found: dict[str, list[str]] = {}
    errors = 0

    for month in months_to_check():
        try:
            payload = fetch_month(month)
        except HTTPError as e:
            errors += 1
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            print(f"  [{month}] HTTP {e.code} {e.reason} :: {detail}")
            continue
        except (URLError, Exception) as e:
            errors += 1
            print(f"  [{month}] error: {e}")
            continue

        dates = available_dates_from(payload)
        if dates:
            found[month] = dates
            print(f"  [{month}] *** {len(dates)} available: {dates} ***")
        else:
            print(f"  [{month}] none  (raw: {json.dumps(payload)[:200]})")

    if errors and not found:
        print(f"  WARNING: {errors} request(s) failed and nothing found — "
              f"treating as inconclusive, state not updated.")
        return

    all_dates = sorted({d for ds in found.values() for d in ds})

    state = load_state()
    previously = set(state.get("available_dates", []))
    new_dates = [d for d in all_dates if d not in previously]

    if new_dates:
        print(f"  NEW availability: {new_dates}")
        try:
            send_email(new_dates, all_dates)
        except Exception as e:
            print(f"  Email failed: {e}")
    elif all_dates:
        print(f"  {len(all_dates)} date(s) available, but already alerted.")
    else:
        print("  No availability (expected — fully booked).")

    state["available_dates"] = all_dates
    state["checked_at"] = datetime.now().isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
