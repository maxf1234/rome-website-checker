#!/usr/bin/env python3
"""
Acuity Scheduling Availability Monitor — DISCOVERY MODE v7 (browser)

Reverse-engineering the SPA's auth (X-Secondo-Session comes from an opaque
bundle constant) hit diminishing returns. Driving a real browser sidesteps
it entirely: the page authenticates itself, and we can both read the
rendered calendar and capture the exact availability API call it makes.
"""

import json
from datetime import datetime
from playwright.sync_api import sync_playwright

BOOKING_URL = (
    "https://app.acuityscheduling.com/schedule/ce551904"
    "/appointment/71567018/calendar/11158185"
)

INTERESTING = ("/api/scheduling/v1", "availability", "schedule.php")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Acuity discovery v7 — headless browser")

    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
            locale="en-US",
        )
        page = ctx.new_page()

        def on_response(resp):
            url = resp.url
            if not any(k in url for k in INTERESTING):
                return
            entry = {
                "url": url,
                "status": resp.status,
                "request_headers": dict(resp.request.headers),
                "method": resp.request.method,
            }
            try:
                entry["body"] = resp.text()[:4000]
            except Exception as e:
                entry["body"] = f"(unreadable: {e})"
            captured.append(entry)

        page.on("response", on_response)

        print(f"  Loading {BOOKING_URL}")
        page.goto(BOOKING_URL, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(6000)

        print(f"\n  Page title: {page.title()}")

        # ── What the user actually sees ──
        try:
            body_text = page.inner_text("body")
        except Exception as e:
            body_text = f"(could not read body: {e})"
        print(f"\n  ── RENDERED PAGE TEXT ──\n{body_text[:5000]}")

        # ── Calendar day buttons and their state ──
        print("\n  ── CALENDAR DAY ELEMENTS ──")
        for sel in ['[role="gridcell"]', "button[aria-label]", "[class*=day]",
                    "[data-testid*=day]", "[class*=Day]"]:
            try:
                els = page.query_selector_all(sel)
            except Exception:
                continue
            if not els:
                continue
            print(f"\n    selector {sel}: {len(els)} elements (first 25)")
            for el in els[:25]:
                try:
                    txt = (el.inner_text() or "").strip().replace("\n", " ")
                    aria = el.get_attribute("aria-label")
                    disabled = el.get_attribute("disabled")
                    aria_dis = el.get_attribute("aria-disabled")
                    cls = (el.get_attribute("class") or "")[:70]
                    print(f"      text={txt[:30]!r} aria={aria!r} "
                          f"disabled={disabled} aria-disabled={aria_dis} class={cls!r}")
                except Exception:
                    pass

        page.screenshot(path="page.png", full_page=True)
        print("\n  Screenshot saved to page.png")

        browser.close()

    # ── The API calls the page made ──
    print(f"\n\n  ── CAPTURED API CALLS ({len(captured)}) ──")
    for c in captured:
        print(f"\n  {c['method']} {c['url']}")
        print(f"    status: {c['status']}")
        print(f"    request headers: {json.dumps(c['request_headers'], indent=6)[:1500]}")
        print(f"    response body: {c['body'][:3000]}")


if __name__ == "__main__":
    main()
