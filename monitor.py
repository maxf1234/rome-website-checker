#!/usr/bin/env python3
"""
Colosseum Ticketing Monitor
Checks the MidaTicket calendar AJAX endpoint behind ticketing.colosseo.it for
August 7 availability on two Full Experience event pages, and emails a list
of recipients as soon as any slot opens up. The site's Octofence WAAP blocks
requests from datacenter IPs outright, so calls are routed through ScraperAPI
(residential IP pool) instead of hitting the site directly.
"""

import json
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

CALENDAR_URL = "https://ticketing.colosseo.it/mtajax/calendars_month"

EVENTS = {
    "Full Experience - Sotterranei e Arena": {
        "page_id": "225",
        "page_url": "https://ticketing.colosseo.it/en/eventi/full-experience-sotterranei-e-arena/",
    },
    "Full Experience - Percorso Didattico": {
        "page_id": "753",
        "page_url": "https://ticketing.colosseo.it/en/eventi/full-experience-sotterranei-e-arena-percorso-didattico/",
    },
}

TARGET_DATE = "2026-08-07"
TARGET_YEAR = 2026
TARGET_MONTH = 8

STATE_FILE = "state.json"

SCRAPER_API_KEY = os.environ["SCRAPER_API_KEY"]
EMAIL_SENDER    = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD  = os.environ["EMAIL_PASSWORD"]
EMAIL_RECIPIENT = os.environ["EMAIL_RECIPIENT"]
RECIPIENT_LIST  = [e.strip() for e in EMAIL_RECIPIENT.split(",") if e.strip()]

# ─────────────────────────────────────────────


def fetch_calendar_month(page_id: str) -> dict:
    """POST to the calendars_month AJAX endpoint via ScraperAPI (residential
    IP pool), since the site blocks datacenter IPs outright at the firewall."""
    body = (
        f"action=midaabc_calendars_month&page={page_id}"
        f"&year={TARGET_YEAR}&month={TARGET_MONTH}"
    ).encode("utf-8")

    proxy_url = (
        f"http://api.scraperapi.com/?api_key={SCRAPER_API_KEY}"
        f"&url={quote(CALENDAR_URL, safe='')}"
    )
    req = Request(
        proxy_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        method="POST",
    )
    with urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def slots_for_target_date(calendar_data: dict) -> list:
    slots = calendar_data.get("data", [])
    return [s for s in slots if s.get("startDateTime", "").startswith(TARGET_DATE)]


def summarize(slots: list) -> dict:
    total_available = sum(max(s.get("capacity", 0), 0) for s in slots)
    available_slots = [s for s in slots if s.get("capacity", 0) > 0]
    return {
        "total_available_capacity": total_available,
        "available_slot_count": len(available_slots),
        "slots": [
            {
                "startDateTime": s.get("startDateTime"),
                "endDateTime": s.get("endDateTime"),
                "capacity": s.get("capacity"),
                "originalCapacity": s.get("originalCapacity"),
                "calendarGroupLabel": s.get("calendarGroupLabel"),
            }
            for s in slots
        ],
    }


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_email(changes: list, current_by_event: dict) -> None:
    subject = f"Colosseum tickets — Aug 7 availability opened! ({len(changes)} event(s))"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body_parts = [
        f"Availability opened up for August 7 on the Colosseum ticketing site!",
        f"Detected at: {timestamp}",
        "",
    ]
    for name in changes:
        summary = current_by_event[name]
        url = EVENTS[name]["page_url"]
        body_parts.append(f"{name}")
        body_parts.append(f"  {summary['available_slot_count']} slot(s), "
                           f"{summary['total_available_capacity']} total spot(s) available")
        for s in summary["slots"]:
            if s["capacity"] > 0:
                body_parts.append(
                    f"    {s['startDateTime']} - {s['endDateTime']}: "
                    f"{s['capacity']} spot(s) ({s.get('calendarGroupLabel', '')})"
                )
        body_parts.append(f"  BOOK NOW: {url}")
        body_parts.append("")

    body = "\n".join(body_parts)

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = ", ".join(RECIPIENT_LIST)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, RECIPIENT_LIST, msg.as_string())

    print(f"  Alert sent to {RECIPIENT_LIST}")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Checking Aug 7 availability...")

    state = load_state()
    previous = state.get("events", {})
    current_by_event = {}
    changed_events = []

    for name, cfg in EVENTS.items():
        page_id = cfg["page_id"]
        if not page_id:
            print(f"  Skipping '{name}' — no page_id configured.")
            continue

        try:
            data = fetch_calendar_month(page_id)
        except HTTPError as e:
            print(f"  [{name}] HTTPError: {e.code} {e.reason}")
            try:
                print(f"    Body: {e.read().decode('utf-8', errors='replace')[:2000]}")
            except Exception:
                pass
            continue
        except URLError as e:
            print(f"  [{name}] URLError: {e}")
            continue
        except Exception as e:
            print(f"  [{name}] Unexpected error: {e}")
            continue

        if not data.get("success"):
            print(f"  [{name}] API returned success=false: {json.dumps(data)[:500]}")
            continue

        day_slots = slots_for_target_date(data)
        summary = summarize(day_slots)
        current_by_event[name] = summary

        prev_summary = previous.get(name)
        prev_available = prev_summary.get("total_available_capacity", 0) if prev_summary else 0
        curr_available = summary["total_available_capacity"]

        print(f"  [{name}] {summary['available_slot_count']} slot(s) available, "
              f"{curr_available} total spot(s) (was {prev_available})")

        if curr_available > 0 and curr_available > prev_available:
            changed_events.append(name)

    if changed_events:
        print(f"  Availability opened for: {changed_events} — sending alert...")
        try:
            send_email(changed_events, current_by_event)
        except Exception as e:
            print(f"  Email failed: {e}")
    else:
        print("  No new availability.")

    state["events"] = current_by_event
    state["checked_at"] = datetime.now().isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
