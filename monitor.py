#!/usr/bin/env python3
"""
Acuity Scheduling Availability Monitor — DISCOVERY MODE v2

First pass found the page is reachable (HTTP 200) and revealed the numeric
owner ID (22283479) — the earlier probes 404'd because they used the URL
slug instead. This pass dumps the page's embedded JSON config and probes
Acuity's classic schedule.php endpoints with the correct owner ID.
"""

import json
import re
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

BOOKING_URL = (
    "https://app.acuityscheduling.com/schedule/ce551904"
    "/appointment/71567018/calendar/11158185"
)

SLUG                = "ce551904"
OWNER_ID            = "22283479"
APPOINTMENT_TYPE_ID = "71567018"
CALENDAR_ID         = "11158185"

MONTHS = ["2026-07", "2026-08"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

AJAX_HEADERS = dict(HEADERS)
AJAX_HEADERS["Accept"] = "*/*"
AJAX_HEADERS["X-Requested-With"] = "XMLHttpRequest"
AJAX_HEADERS["Referer"] = BOOKING_URL


def fetch(url: str, headers: dict, timeout: int = 30) -> tuple[int, str]:
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def probe(label: str, url: str) -> None:
    print(f"\n  PROBE [{label}]")
    print(f"    URL: {url}")
    try:
        status, text = fetch(url, AJAX_HEADERS)
    except HTTPError as e:
        print(f"    HTTPError {e.code} {e.reason}")
        try:
            print(f"    Body: {e.read().decode('utf-8', errors='replace')[:400]}")
        except Exception:
            pass
        return
    except Exception as e:
        print(f"    Error: {e}")
        return

    print(f"    Status: {status}, length: {len(text)}")
    s = text.strip()
    if s.startswith("{") or s.startswith("["):
        print(f"    JSON: {s[:2500]}")
    else:
        # Calendar HTML — surface the availability-bearing bits
        classes = sorted(set(re.findall(r'class="([^"]*(?:day|avail|time|slot)[^"]*)"', s, re.I)))
        print(f"    HTML. Interesting classes: {classes[:25]}")
        for phrase in ["no times", "not available", "no availability",
                       "fully booked", "sold out", "no appointments", "unavailable"]:
            if phrase in s.lower():
                print(f"    Contains phrase: '{phrase}'")
        print(f"    First 1500 chars: {s[:1500]}")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Acuity discovery v2")

    # ── 1. Full page dump ──
    print("\n### STEP 1: full booking page ###")
    html = ""
    try:
        status, html = fetch(BOOKING_URL, HEADERS)
        print(f"  Status: {status}, length: {len(html)}")
    except Exception as e:
        print(f"  Error: {e}")

    if html:
        print("\n  ── FULL PAGE HTML ──")
        chunk = 3000
        for i in range(0, len(html), chunk):
            print(f"  [chars {i}-{i+chunk}]\n{html[i:i+chunk]}")

        # Pull out the appointment type entry matching our URL
        for m in re.finditer(r'\{"id":' + APPOINTMENT_TYPE_ID + r'.{0,700}', html):
            print(f"\n  APPOINTMENT TYPE {APPOINTMENT_TYPE_ID} entry: {m.group(0)}")

    # ── 2. Probe classic endpoints with the REAL owner id ──
    print("\n\n### STEP 2: classic schedule.php probes (owner=%s) ###" % OWNER_ID)
    for month in MONTHS:
        probe(
            f"showCalendar {month}",
            f"https://app.acuityscheduling.com/schedule.php?action=showCalendar"
            f"&fulldate=1&owner={OWNER_ID}&type={APPOINTMENT_TYPE_ID}"
            f"&calendarID={CALENDAR_ID}&month={month}",
        )
        probe(
            f"availableDates {month}",
            f"https://app.acuityscheduling.com/schedule.php?action=availableDates"
            f"&owner={OWNER_ID}&type={APPOINTMENT_TYPE_ID}"
            f"&calendarID={CALENDAR_ID}&month={month}",
        )

    probe(
        "showSelect (type chooser)",
        f"https://app.acuityscheduling.com/schedule.php?action=showSelect&owner={OWNER_ID}",
    )
    probe(
        "plain schedule.php owner page",
        f"https://app.acuityscheduling.com/schedule.php?owner={OWNER_ID}",
    )


if __name__ == "__main__":
    main()
