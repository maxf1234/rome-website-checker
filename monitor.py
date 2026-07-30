#!/usr/bin/env python3
"""
Acuity Scheduling Availability Monitor — DISCOVERY MODE v4

v3 found the API base `/api/scheduling/v1` and that the SPA calls
`availability.month.get` / `availability.times.get` from an endpoint
registry. This pass extracts the exact URL templates from the bundle and
probes the most likely availability endpoints.
"""

import re
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError

BOOKING_URL = (
    "https://app.acuityscheduling.com/schedule/ce551904"
    "/appointment/71567018/calendar/11158185"
)

SLUG                = "ce551904"
OWNER_ID            = "22283479"
APPOINTMENT_TYPE_ID = "71567018"
CALENDAR_ID         = "11158185"
MONTH               = "2026-08"

BASE = "https://app.acuityscheduling.com/api/scheduling/v1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BOOKING_URL,
    "X-Requested-With": "XMLHttpRequest",
}


def get(url: str, headers: dict, timeout: int = 60) -> tuple[int, str]:
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def probe(label: str, url: str) -> None:
    print(f"\n  PROBE [{label}]")
    print(f"    {url}")
    try:
        status, text = get(url, HEADERS)
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        print(f"    HTTP {e.code} {e.reason} :: {body}")
        return
    except Exception as e:
        print(f"    Error: {e}")
        return
    print(f"    HTTP {status}, {len(text)} chars")
    print(f"    Body: {text[:2000]}")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Acuity discovery v4")

    # ── 1. Find the endpoint registry in the bundle ──
    try:
        _, html = get(BOOKING_URL, HEADERS)
    except Exception as e:
        print(f"  page load failed: {e}")
        html = ""

    scripts = [s for s in re.findall(r'<script[^>]*src=["\']?([^"\'\s>]+)', html, re.I)
               if s.endswith(".js") and "recaptcha" not in s]

    for src in scripts:
        url = src if src.startswith("http") else f"https://app.acuityscheduling.com{src}"
        if "scheduling-pylon" not in url:
            continue
        print(f"\n### Bundle: {url}")
        try:
            _, js = get(url, HEADERS)
        except Exception as e:
            print(f"    error: {e}")
            continue
        print(f"    {len(js)} chars")

        # The endpoint registry: look for `availability:{` and nearby definitions
        for pat in [r"availability\s*:\s*\{", r"month\s*:\s*\{\s*get", r"times\s*:\s*\{\s*get"]:
            for m in list(re.finditer(pat, js))[:4]:
                a, b = max(0, m.start() - 400), min(len(js), m.end() + 1600)
                print(f"\n    [{pat}] ...{js[a:b]}...")

        # How is the API base used?
        for m in list(re.finditer(re.escape("/api/scheduling/v1"), js))[:5]:
            a, b = max(0, m.start() - 500), min(len(js), m.end() + 500)
            print(f"\n    [base usage] ...{js[a:b]}...")

    # ── 2. Probe likely availability endpoints ──
    print("\n\n### Probing candidate availability endpoints ###")
    qs_variants = [
        f"appointmentTypeID={APPOINTMENT_TYPE_ID}&calendarID={CALENDAR_ID}&month={MONTH}",
        f"appointmentTypeId={APPOINTMENT_TYPE_ID}&calendarId={CALENDAR_ID}&month={MONTH}",
        f"owner={OWNER_ID}&appointmentTypeID={APPOINTMENT_TYPE_ID}&calendarID={CALENDAR_ID}&month={MONTH}",
        f"ownerKey={SLUG}&appointmentTypeID={APPOINTMENT_TYPE_ID}&calendarID={CALENDAR_ID}&month={MONTH}",
    ]
    for i, qs in enumerate(qs_variants):
        probe(f"availability/dates v{i}", f"{BASE}/availability/dates?{qs}")
        probe(f"availability/month v{i}", f"{BASE}/availability/month?{qs}")

    probe("catalog", f"{BASE}/catalog/{SLUG}")
    probe("schedule root", f"{BASE}/schedule/{SLUG}")


if __name__ == "__main__":
    main()
