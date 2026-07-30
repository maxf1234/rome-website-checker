#!/usr/bin/env python3
"""
Consulate Appointment Monitor — Consulado-Geral de Portugal em Newark

Watches the Acuity/Squarespace Scheduling booking page for ANY appointment
availability and emails the moment a slot opens.

GitHub's cron granularity bottoms out at ~5 minutes, so for minute-level
checking this runs as a long-lived job: one workflow run stays alive and
polls on an internal 60s loop until its deadline, at which point the next
scheduled run takes over.

Endpoint/auth were captured by instrumenting the real page in a headless
browser; see README.md for the details and API quirks.
"""

import json
import os
import smtplib
import sys
import time
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

APPOINTMENT_NAME = ("Application for Portuguese Nationality "
                    "for Children of Portuguese Citizens")

API_URL = "https://app.acuityscheduling.com/api/scheduling/v1/availability/month"

MONTHS_AHEAD = int(os.environ.get("MONTHS_AHEAD", "6"))
STATE_FILE   = "state.json"

# Long-poll settings
CHECK_INTERVAL_SEC = int(os.environ.get("CHECK_INTERVAL_SEC", "60"))
RUN_DURATION_SEC   = int(os.environ.get("RUN_DURATION_SEC", str(32 * 60)))

EMAIL_SENDER    = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD  = os.environ["EMAIL_PASSWORD"]
EMAIL_RECIPIENT = os.environ["EMAIL_RECIPIENT"]
RECIPIENT_LIST  = [e.strip() for e in EMAIL_RECIPIENT.split(",") if e.strip()]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US",
    "Referer": BOOKING_URL,
    "x-secondo-owner": SLUG,
    "x-secondo-session": str(uuid.uuid4()),
}

BAR = "═" * 64


def log(msg: str = "") -> None:
    print(msg, flush=True)


def clock() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ─────────────────────────────────────────────
#  AVAILABILITY CHECK
# ─────────────────────────────────────────────

def months_to_check() -> list[str]:
    """Current month (as today) plus the next MONTHS_AHEAD (as the 1st).

    The API needs a full YYYY-MM-DD date and rejects months before the
    current one, so the current month is represented by today's date.
    """
    today = date.today()
    out = [today.isoformat()]
    y, m = today.year, today.month
    for _ in range(MONTHS_AHEAD):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        out.append(f"{y:04d}-{m:02d}-01")
    return out


def fetch_month(month: str) -> dict:
    params = {
        "owner": SLUG,
        "appointmentTypeId": APPOINTMENT_TYPE_ID,
        "calendarId": CALENDAR_ID,
        "timezone": TIMEZONE,
        "month": month,
    }
    req = Request(f"{API_URL}?{urlencode(params)}", headers=HEADERS, method="GET")
    with urlopen(req, timeout=45) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw.strip() else {}


def available_dates_from(payload) -> list[str]:
    """The app's own rule: keys whose value is truthy are available dates."""
    if isinstance(payload, dict):
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


def run_check() -> tuple[list[str], int, list[str]]:
    """Returns (available_dates, error_count, error_messages)."""
    dates: set[str] = set()
    errors: list[str] = []

    for month in months_to_check():
        try:
            dates.update(available_dates_from(fetch_month(month)))
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:120]
            except Exception:
                pass
            errors.append(f"{month}: HTTP {e.code} {detail}")
        except URLError as e:
            errors.append(f"{month}: network error {e.reason}")
        except Exception as e:
            errors.append(f"{month}: {type(e).__name__} {e}")

    return sorted(dates), len(errors), errors


# ─────────────────────────────────────────────
#  STATE + EMAIL
# ─────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(dates: list[str]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump({"available_dates": dates,
                   "checked_at": datetime.now().isoformat()}, f, indent=2)


def send_email(new_dates: list[str], all_dates: list[str]) -> None:
    subject = f"🚨 Consulate appointment OPEN — {', '.join(new_dates[:3])}"
    if len(new_dates) > 3:
        subject += f" +{len(new_dates) - 3} more"

    body = f"""APPOINTMENT AVAILABILITY JUST OPENED

Appointment: {APPOINTMENT_NAME}
Location:    Consulado-Geral de Portugal em Newark
Detected:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

NEWLY AVAILABLE
{chr(10).join('  • ' + d for d in new_dates)}

ALL CURRENTLY AVAILABLE
{chr(10).join('  • ' + d for d in all_dates)}

BOOK NOW:
{BOOKING_URL}

These slots go fast — book immediately.
"""
    msg = MIMEMultipart()
    msg["From"], msg["Subject"] = EMAIL_SENDER, subject
    msg["To"] = ", ".join(RECIPIENT_LIST)
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, RECIPIENT_LIST, msg.as_string())


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────

def main() -> None:
    months = months_to_check()
    deadline = time.time() + RUN_DURATION_SEC

    log(BAR)
    log("  CONSULATE APPOINTMENT MONITOR")
    log("  Consulado-Geral de Portugal em Newark")
    log(f"  {APPOINTMENT_NAME}")
    log(BAR)
    log(f"  Started        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"  Checking every {CHECK_INTERVAL_SEC}s "
        f"for {RUN_DURATION_SEC // 60} min")
    log(f"  Scanning       {len(months)} months "
        f"({months[0]} → {months[-1]})")
    log(f"  Alerts to      {', '.join(RECIPIENT_LIST)}")
    log(BAR)
    log("")

    known = set(load_state().get("available_dates", []))
    if known:
        log(f"  Previously known available dates: {sorted(known)}")
        log("")

    check_num = 0
    alerts_sent = 0
    consecutive_errors = 0

    while time.time() < deadline:
        check_num += 1
        dates, err_count, err_msgs = run_check()

        if err_count and not dates:
            consecutive_errors += 1
            log(f"  [{clock()}] check #{check_num:<3}  ⚠ inconclusive — "
                f"all {err_count} request(s) failed")
            for m in err_msgs[:2]:
                log(f"                          └─ {m}")
            if consecutive_errors >= 5:
                log(f"  [{clock()}] {consecutive_errors} failed checks in a row "
                    f"— the API may have changed.")
        else:
            consecutive_errors = 0
            new_dates = [d for d in dates if d not in known]

            if new_dates:
                log("")
                log("  " + "★" * 60)
                log(f"  [{clock()}] check #{check_num:<3}  AVAILABILITY FOUND!")
                for d in new_dates:
                    log(f"                          → {d}")
                log("  " + "★" * 60)
                try:
                    send_email(new_dates, dates)
                    alerts_sent += 1
                    log(f"  [{clock()}] ✉ email sent to {', '.join(RECIPIENT_LIST)}")
                except Exception as e:
                    log(f"  [{clock()}] ✗ EMAIL FAILED: {e}")
                log("")
                known.update(new_dates)
                save_state(sorted(known))
            elif dates:
                log(f"  [{clock()}] check #{check_num:<3}  "
                    f"{len(dates)} date(s) open (already alerted)")
            else:
                suffix = f"  ({err_count} month(s) errored)" if err_count else ""
                log(f"  [{clock()}] check #{check_num:<3}  no availability{suffix}")

            if set(dates) != known and not new_dates:
                known = set(dates)
                save_state(sorted(known))

        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(CHECK_INTERVAL_SEC, remaining))

    log("")
    log(BAR)
    log(f"  Run complete — {check_num} checks, {alerts_sent} alert(s) sent")
    log(f"  Currently available: {sorted(known) if known else 'none'}")
    log(f"  Next run takes over shortly.")
    log(BAR)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n  Interrupted — exiting cleanly.")
        sys.exit(0)
