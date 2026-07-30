#!/usr/bin/env python3
"""
Acuity Scheduling Availability Monitor — DISCOVERY MODE v3

The booking page is a Squarespace Scheduling React SPA, so availability
comes from a JSON API the bundle calls at runtime. Classic schedule.php
endpoints are dead for this page. This pass downloads the JS bundle(s)
referenced by the page and greps them for the actual API paths, then
probes the best candidates.
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

AJAX_HEADERS = dict(HEADERS)
AJAX_HEADERS["X-Requested-With"] = "XMLHttpRequest"
AJAX_HEADERS["Referer"] = BOOKING_URL

# Terms that would appear near availability API paths
KEYWORDS = [
    "datesAvailable", "availableDates", "availability", "availableTimes",
    "times", "openings", "slots", "calendar",
]


def get(url: str, headers: dict, timeout: int = 60) -> tuple[int, str]:
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Acuity discovery v3 — JS bundle analysis")

    # ── 1. Get script URLs from the page ──
    try:
        _, html = get(BOOKING_URL, HEADERS)
    except Exception as e:
        print(f"  Failed to load page: {e}")
        return

    scripts = re.findall(r'<script[^>]*src=["\']?([^"\'\s>]+)', html, re.I)
    scripts = [s for s in scripts if s.endswith(".js")]
    print(f"\n  Script URLs found ({len(scripts)}):")
    for s in scripts:
        print(f"    {s}")

    # ── 2. Download and grep each bundle for API paths ──
    all_paths = set()
    for src in scripts:
        if "recaptcha" in src or "trustarc" in src:
            continue
        url = src if src.startswith("http") else f"https://app.acuityscheduling.com{src}"
        print(f"\n### Bundle: {url}")
        try:
            status, js = get(url, HEADERS)
        except Exception as e:
            print(f"    Error: {e}")
            continue
        print(f"    Status {status}, {len(js)} chars")

        # Absolute/relative API-ish path literals
        paths = set(re.findall(r'["\'`](/(?:api|schedule)[A-Za-z0-9/_\-.{}$:]*)["\'`]', js))
        # Template-literal paths with interpolation
        paths |= set(re.findall(r'["\'`](/[A-Za-z0-9/_\-.]*\$\{[^}`]*\}[A-Za-z0-9/_\-.${}]*)["\'`]', js))
        all_paths |= paths
        print(f"    API-ish path literals: {len(paths)}")
        for p in sorted(paths)[:60]:
            print(f"      {p}")

        print("    Keyword hits with surrounding context:")
        for kw in KEYWORDS:
            for m in list(re.finditer(re.escape(kw), js))[:3]:
                a, b = max(0, m.start() - 130), min(len(js), m.end() + 130)
                snippet = js[a:b].replace("\n", " ")
                print(f"      [{kw}] ...{snippet}...")

    print(f"\n\n### All distinct API-ish paths across bundles ({len(all_paths)}) ###")
    for p in sorted(all_paths):
        print(f"  {p}")


if __name__ == "__main__":
    main()
