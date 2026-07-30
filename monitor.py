#!/usr/bin/env python3
"""
Acuity Scheduling Availability Monitor — DISCOVERY MODE v5

v4 confirmed `/api/scheduling/v1/availability/month` is the right endpoint
(401 Unauthorized, not 404). This pass works out the auth: first tries
carrying session cookies from loading the booking page, then greps the
bundle for whatever header/token the SPA attaches.
"""

import http.cookiejar
import re
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
    "Accept-Language": "en-US,en;q=0.9",
}

API_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BOOKING_URL,
    "X-Requested-With": "XMLHttpRequest",
}

jar = http.cookiejar.CookieJar()
opener = build_opener(HTTPCookieProcessor(jar))


def get(url: str, headers: dict, timeout: int = 60) -> tuple[int, str]:
    req = Request(url, headers=headers, method="GET")
    with opener.open(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def probe(label: str, url: str, extra_headers: dict | None = None) -> None:
    h = dict(API_HEADERS)
    if extra_headers:
        h.update(extra_headers)
    print(f"\n  PROBE [{label}]")
    print(f"    {url}")
    if extra_headers:
        print(f"    extra headers: {list(extra_headers.keys())}")
    try:
        status, text = get(url, h)
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        print(f"    HTTP {e.code} {e.reason} :: {body}")
        return
    except Exception as e:
        print(f"    Error: {e}")
        return
    print(f"    HTTP {status}, {len(text)} chars")
    print(f"    Body: {text[:2500]}")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Acuity discovery v5 — auth")

    # ── 1. Load booking page to establish a session ──
    print("\n### STEP 1: load page for cookies ###")
    html = ""
    try:
        status, html = get(BOOKING_URL, PAGE_HEADERS)
        print(f"  page HTTP {status}, {len(html)} chars")
    except Exception as e:
        print(f"  page load error: {e}")

    print(f"  Cookies obtained ({len(jar)}):")
    for c in jar:
        val = c.value or ""
        print(f"    {c.name} = {val[:40]}{'...' if len(val) > 40 else ''}  (domain={c.domain})")

    # Any token embedded directly in the page?
    for pat in [r'["\']?(?:csrf|token|apiKey|api_key|authToken)["\']?\s*[:=]\s*["\']([A-Za-z0-9._\-]{16,})["\']',
                r'window\.__[A-Z_]+__\s*=\s*(\{.{0,600})']:
        for m in list(re.finditer(pat, html, re.I))[:5]:
            print(f"  page token candidate: {m.group(0)[:200]}")

    # ── 2. Retry the availability endpoint WITH session cookies ──
    print("\n\n### STEP 2: availability/month with session cookies ###")
    param_sets = [
        f"appointmentTypeID={APPOINTMENT_TYPE_ID}&calendarID={CALENDAR_ID}&month={MONTH}",
        f"appointmentTypeId={APPOINTMENT_TYPE_ID}&calendarId={CALENDAR_ID}&month={MONTH}",
        f"owner={OWNER_ID}&appointmentTypeID={APPOINTMENT_TYPE_ID}&calendarID={CALENDAR_ID}&month={MONTH}",
        f"ownerKey={SLUG}&appointmentTypeID={APPOINTMENT_TYPE_ID}&calendarID={CALENDAR_ID}&month={MONTH}",
    ]
    for i, qs in enumerate(param_sets):
        probe(f"month params#{i}", f"{BASE}/availability/month?{qs}")

    # Some Squarespace Scheduling deployments key off an owner header
    probe("month + X-Secondo-Owner", f"{BASE}/availability/month?{param_sets[0]}",
          {"X-Secondo-Owner": OWNER_ID})
    probe("month + owner-key header", f"{BASE}/availability/month?{param_sets[0]}",
          {"X-Owner-Key": SLUG})

    # ── 3. Grep bundle for auth mechanics ──
    print("\n\n### STEP 3: bundle auth grep ###")
    scripts = [s for s in re.findall(r'<script[^>]*src=["\']?([^"\'\s>]+)', html, re.I)
               if s.endswith(".js") and "scheduling-pylon" in s and "errorReporter" not in s]
    for src in scripts:
        url = src if src.startswith("http") else f"https://app.acuityscheduling.com{src}"
        print(f"\n  Bundle: {url}")
        try:
            _, js = get(url, PAGE_HEADERS)
        except Exception as e:
            print(f"    error: {e}")
            continue
        print(f"    {len(js)} chars")

        for kw in ["Authorization", "Bearer", "X-Secondo", "authToken",
                   "availability/month", "ownerKey:", "X-CSRF"]:
            hits = list(re.finditer(re.escape(kw), js))[:3]
            if not hits:
                continue
            print(f"    --- {kw} ({len(hits)} shown) ---")
            for m in hits:
                a, b = max(0, m.start() - 350), min(len(js), m.end() + 350)
                print(f"      ...{js[a:b]}...")


if __name__ == "__main__":
    main()
