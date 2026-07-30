#!/usr/bin/env python3
"""
Acuity Scheduling Availability Monitor — DISCOVERY MODE

Probes the target Acuity booking page to learn how it exposes availability
before the real monitoring logic is written. Dumps page structure, embedded
JSON/config, and the results of probing Acuity's known availability API
endpoint shapes.

Run this via the GitHub Action once, read the job logs, then replace this
with the real check.
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
APPOINTMENT_TYPE_ID = "71567018"
CALENDAR_ID         = "11158185"

MONTHS = ["2026-07", "2026-08", "2026-09"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

JSON_HEADERS = dict(HEADERS)
JSON_HEADERS["Accept"] = "application/json, text/plain, */*"
JSON_HEADERS["X-Requested-With"] = "XMLHttpRequest"
JSON_HEADERS["Referer"] = BOOKING_URL

# Interesting keys that would indicate availability data
AVAILABILITY_HINTS = [
    "availableDates", "available", "slots", "times", "openings",
    "soldOut", "isAvailable", "noTimes", "calendarID", "appointmentTypeID",
    "owner", "firstAvailable",
]


def fetch(url: str, headers: dict, timeout: int = 30) -> tuple[int, str]:
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def probe(label: str, url: str, headers: dict) -> None:
    print(f"  PROBE [{label}]")
    print(f"    URL: {url}")
    try:
        status, text = fetch(url, headers)
    except HTTPError as e:
        print(f"    HTTPError {e.code} {e.reason}")
        try:
            print(f"    Body: {e.read().decode('utf-8', errors='replace')[:600]}")
        except Exception:
            pass
        return
    except URLError as e:
        print(f"    URLError: {e}")
        return
    except Exception as e:
        print(f"    Error: {e}")
        return

    print(f"    Status: {status}, length: {len(text)}")
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        print(f"    JSON body: {stripped[:1500]}")
    else:
        print(f"    Non-JSON body (first 600): {stripped[:600]}")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Acuity discovery run")
    print(f"BOOKING_URL: {BOOKING_URL}\n")

    # ── 1. Fetch the booking page itself ──
    print("### STEP 1: main booking page ###")
    html = ""
    try:
        status, html = fetch(BOOKING_URL, HEADERS)
        print(f"  Status: {status}")
        print(f"  Length: {len(html)}")
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        print(f"  Title: {m.group(1).strip() if m else '(none)'}")
    except HTTPError as e:
        print(f"  HTTPError {e.code} {e.reason}")
        try:
            html = e.read().decode("utf-8", errors="replace")
            print(f"  Body (first 1000): {html[:1000]}")
        except Exception:
            pass
    except Exception as e:
        print(f"  Error: {e}")

    if html:
        # Owner ID is needed for the classic schedule.php endpoints
        for pat in [r'owner["\']?\s*[:=]\s*["\']?(\d{4,})',
                    r'data-owner=["\'](\d{4,})["\']',
                    r'ownerId["\']?\s*[:=]\s*["\']?(\d{4,})']:
            found = re.findall(pat, html, re.I)
            if found:
                print(f"  Owner ID candidates via /{pat}/: {sorted(set(found))[:5]}")

        print("\n  Availability-related keywords present in page:")
        for hint in AVAILABILITY_HINTS:
            n = len(re.findall(re.escape(hint), html, re.I))
            if n:
                print(f"    {hint}: {n}")

        # Any inline JSON blobs
        for pat, label in [
            (r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', "application/json"),
            (r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;', "__INITIAL_STATE__"),
            (r'window\.acuity\w*\s*=\s*(\{.*?\})\s*;', "window.acuity*"),
        ]:
            for mm in re.finditer(pat, html, re.I | re.S):
                print(f"\n  JSON blob [{label}] (first 1200): {mm.group(1)[:1200]}")

        # Look for API paths referenced in the page
        api_paths = sorted(set(re.findall(r'["\'](/api/[A-Za-z0-9/_\-{}.]+)["\']', html)))
        print(f"\n  /api/ paths referenced in page ({len(api_paths)}):")
        for p in api_paths[:40]:
            print(f"    {p}")

        # Telltale 'no availability' phrasing
        for phrase in ["no times", "not available", "no availability",
                       "fully booked", "sold out", "no appointments"]:
            if phrase in html.lower():
                print(f"  NOTE: page contains phrase '{phrase}'")

        mid = len(html) // 2
        print(f"\n  Raw HTML sample (middle 1200 chars):\n{html[mid:mid+1200]}")

    # ── 2. Probe candidate availability endpoints ──
    print("\n### STEP 2: probing candidate availability endpoints ###")
    for month in MONTHS:
        probe(
            f"scheduling-page availability/dates {month}",
            f"https://app.acuityscheduling.com/api/scheduling-page/{SLUG}"
            f"/availability/dates?appointmentTypeId={APPOINTMENT_TYPE_ID}"
            f"&calendarId={CALENDAR_ID}&month={month}",
            JSON_HEADERS,
        )
        probe(
            f"classic showCalendar {month}",
            f"https://app.acuityscheduling.com/schedule.php?action=showCalendar"
            f"&fulldate=1&owner={SLUG}&type={APPOINTMENT_TYPE_ID}"
            f"&calendarID={CALENDAR_ID}&month={month}",
            JSON_HEADERS,
        )

    probe(
        "appointment-types",
        f"https://app.acuityscheduling.com/api/scheduling-page/{SLUG}/appointment-types",
        JSON_HEADERS,
    )
    probe(
        "scheduling-page root",
        f"https://app.acuityscheduling.com/api/scheduling-page/{SLUG}",
        JSON_HEADERS,
    )


if __name__ == "__main__":
    main()
