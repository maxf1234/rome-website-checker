#!/usr/bin/env python3
"""
Acuity Scheduling Availability Monitor — DISCOVERY MODE v6

v5 found the auth headers the SPA attaches: `X-Secondo-Session` (set as an
axios default) and `X-Secondo-Owner`, plus the real endpoint constants
(/availability/month, /availability/times) and plural param names
(appointmentTypeIds, calendarIds). This pass probes that combination and
greps for how the session value is produced.
"""

import http.cookiejar
import re
import uuid
from datetime import datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
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

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

PAGE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

API_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": BOOKING_URL,
    "Origin": "https://app.acuityscheduling.com",
    "X-Requested-With": "XMLHttpRequest",
}

jar = http.cookiejar.CookieJar()
opener = build_opener(HTTPCookieProcessor(jar))


def get(url: str, headers: dict, timeout: int = 60) -> tuple[int, str]:
    req = Request(url, headers=headers, method="GET")
    with opener.open(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def probe(label: str, url: str, extra: dict) -> bool:
    h = dict(API_HEADERS)
    h.update(extra)
    print(f"\n  [{label}]")
    print(f"    {url}")
    print(f"    headers: { {k: v for k, v in extra.items()} }")
    try:
        status, text = get(url, h)
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:250]
        except Exception:
            pass
        print(f"    HTTP {e.code} :: {body}")
        return False
    except Exception as e:
        print(f"    Error: {e}")
        return False
    print(f"    *** HTTP {status}, {len(text)} chars ***")
    print(f"    Body: {text[:3000]}")
    return True


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Acuity discovery v6 — Secondo headers")

    try:
        _, html = get(BOOKING_URL, PAGE_HEADERS)
    except Exception as e:
        print(f"  page load error: {e}")
        html = ""

    # window.BUSINESS holds owner context the interceptor reads
    for m in list(re.finditer(r"window\.BUSINESS\s*=\s*(\{.{0,1500})", html, re.S))[:2]:
        print(f"\n  window.BUSINESS = {m.group(1)[:1500]}")
    for m in list(re.finditer(r"BUSINESS", html))[:6]:
        a, b = max(0, m.start() - 200), min(len(html), m.end() + 400)
        print(f"\n  [BUSINESS ctx] ...{html[a:b]}...")

    session = str(uuid.uuid4())
    print(f"\n  Using generated X-Secondo-Session: {session}")

    plural = f"appointmentTypeIds={APPOINTMENT_TYPE_ID}&calendarIds={CALENDAR_ID}&month={MONTH}"
    singular = f"appointmentTypeID={APPOINTMENT_TYPE_ID}&calendarID={CALENDAR_ID}&month={MONTH}"

    print("\n\n### Probing /availability/month with Secondo headers ###")
    ok = False
    for owner_val in (SLUG, OWNER_ID):
        for qs_label, qs in (("plural", plural), ("singular", singular)):
            ok |= probe(
                f"owner={owner_val} {qs_label} +session",
                f"{BASE}/availability/month?{qs}",
                {"X-Secondo-Owner": owner_val, "X-Secondo-Session": session},
            )
            ok |= probe(
                f"owner={owner_val} {qs_label} (no session)",
                f"{BASE}/availability/month?{qs}",
                {"X-Secondo-Owner": owner_val},
            )

    # ── Grep for how X-Secondo-Session's value is produced ──
    print("\n\n### Bundle grep: session value + owner interceptor ###")
    scripts = [s for s in re.findall(r'<script[^>]*src=["\']?([^"\'\s>]+)', html, re.I)
               if s.endswith(".js") and "scheduling-pylon" in s and "errorReporter" not in s]
    for src in scripts:
        url = src if src.startswith("http") else f"https://app.acuityscheduling.com{src}"
        try:
            _, js = get(url, PAGE_HEADERS)
        except Exception as e:
            print(f"  bundle error: {e}")
            continue
        for kw in ['X-Secondo-Session', 'sessionStorage', 'X-Secondo-Owner']:
            for m in list(re.finditer(re.escape(kw), js))[:3]:
                a, b = max(0, m.start() - 500), min(len(js), m.end() + 700)
                print(f"\n  --- {kw} ---\n  ...{js[a:b]}...")


if __name__ == "__main__":
    main()
