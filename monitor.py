#!/usr/bin/env python3
"""
Colosseum Ticketing Monitor — DISCOVERY MODE

This first pass does not yet know how ticketing.colosseo.it exposes
per-date availability (server-rendered HTML vs. a JS-driven API call).
Instead of guessing at selectors, it fetches each event page and prints
a structured dump: response status, whether we hit a bot-protection
challenge, any embedded JSON blobs, and any text near the target date
or common Italian/English sold-out/availability keywords.

Run this via the GitHub Action once, read the job logs, and use what it
finds to replace this with real parsing logic.
"""

import json
import re
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

EVENTS = {
    "Full Experience - Sotterranei e Arena":
        "https://ticketing.colosseo.it/en/eventi/full-experience-sotterranei-e-arena/",
    "Full Experience - Percorso Didattico":
        "https://ticketing.colosseo.it/en/eventi/full-experience-sotterranei-e-arena-percorso-didattico/",
}

TARGET_DATE = "2026-08-07"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
    "Accept-Encoding": "identity",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.colosseo.it/",
}

DIAG_URLS = [
    "https://ticketing.colosseo.it/",
    "https://www.colosseo.it/en/",
    "https://ticketing.colosseo.it/api/",
    "https://ticketing.colosseo.it/wp-json/",
    "https://api.ticketing.colosseo.it/",
    "https://api.colosseo.it/",
    "https://booking.colosseo.it/",
    "https://www.coopculture.it/en/colosseo-e-shop.cfm",
]

KEYWORDS = [
    "sold out", "sold-out", "not available", "no availability", "waiting list",
    "esaurito", "non disponibile", "non è disponibile", "posti esauriti",
    "available", "disponibile", "disponibilit",
]

JSON_BLOB_PATTERNS = [
    (r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', "__NEXT_DATA__"),
    (r'window\.__NUXT__\s*=\s*(\{.*?\});?\s*</script>', "__NUXT__"),
    (r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?\s*</script>', "__INITIAL_STATE__"),
    (r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', "application/json script"),
]


def fetch(url: str) -> tuple[int, str]:
    req = Request(url, headers=HEADERS, method="GET")
    with urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def get_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else "(no <title>)"


def looks_like_challenge(html: str) -> bool:
    markers = ["cf-browser-verification", "Just a moment", "cf_chl", "Attention Required",
               "Checking your browser", "captcha"]
    return any(m.lower() in html.lower() for m in markers)


def find_json_blobs(html: str) -> list[tuple[str, str]]:
    found = []
    for pattern, label in JSON_BLOB_PATTERNS:
        for m in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
            found.append((label, m.group(1)[:2000]))
    return found


def find_date_context(html: str, date_variants: list[str]) -> list[str]:
    snippets = []
    for variant in date_variants:
        for m in re.finditer(re.escape(variant), html, re.IGNORECASE):
            start = max(0, m.start() - 150)
            end = min(len(html), m.end() + 150)
            snippets.append(f"...{html[start:end]}...")
    return snippets


def find_keyword_context(html: str) -> dict[str, int]:
    counts = {}
    for kw in KEYWORDS:
        counts[kw] = len(re.findall(re.escape(kw), html, re.IGNORECASE))
    return {k: v for k, v in counts.items() if v > 0}


def date_variants_for(date_str: str) -> list[str]:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return [
        d.strftime("%Y-%m-%d"),
        d.strftime("%d/%m/%Y"),
        d.strftime("%d-%m-%Y"),
        f'"{d.strftime("%Y-%m-%d")}"',
        f'data-date="{d.strftime("%Y-%m-%d")}"',
        d.strftime("%B %-d").lower(),   # august 7
        d.strftime("%-d %B").lower(),   # 7 august
    ]


def test_calendar_endpoint() -> None:
    """One-off test: replay the captured browser request against the real
    calendar AJAX endpoint to see whether Octofence blocks it purely by IP
    (in which case these cookies won't matter) or needs a valid session."""
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError, URLError

    url = "https://ticketing.colosseo.it/mtajax/calendars_month"
    body = "action=midaabc_calendars_month&page=225&year=2026&month=8".encode("utf-8")
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "cookie": (
            "PHPSESSID=ee8f1f103705ce81f5ee1817a2753ea2; "
            "octofence_jslc=2ffd1556fbcf1322b04f01eb910523307c7b5aa1002ebb68dcc0055b758dfd30; "
            "_of0c681e746413a788=ejBucks1XiQESHARCx9jLS40anIYYgh3AxxxRQ1MPCs; "
            "cookielawinfo-checkbox-necessary=yes; cookielawinfo-checkbox-non-necessary=yes; "
            "_ga=GA1.1.699914594.1785359999; "
            "_ga_M4S0PL1M7R=GS2.1.s1785359998$o1$g0$t1785359998$j60$l0$h0; "
            "qtrans_front_language=en"
        ),
        "origin": "https://ticketing.colosseo.it",
        "referer": "https://ticketing.colosseo.it/en/eventi/full-experience-sotterranei-e-arena/",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
        "x-requested-with": "XMLHttpRequest",
    }
    print("### TEST: replaying captured browser session against calendars_month ###")
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            print(f"  Status: {resp.status}")
            print(f"  Length: {len(text)}")
            print(f"  Body (first 3000 chars): {text[:3000]}")
    except HTTPError as e:
        print(f"  HTTPError: {e.code} {e.reason}")
        try:
            body_text = e.read().decode("utf-8", errors="replace")
            print(f"  Body (first 1000 chars): {body_text[:1000]}")
        except Exception:
            pass
    except URLError as e:
        print(f"  URLError: {e}")
    print()


def main() -> None:
    test_calendar_endpoint()
    print(f"[{datetime.now().isoformat()}] Discovery run — target date {TARGET_DATE}\n")
    variants = date_variants_for(TARGET_DATE)

    print("### DIAGNOSTIC: checking whether the block is domain-wide / IP-based ###")
    for url in DIAG_URLS:
        print(f"  Trying: {url}")
        try:
            status, html = fetch(url)
            print(f"    Status: {status}, length: {len(html)}, title: {get_title(html)}")
            print(f"    Blocked page?: {looks_like_challenge(html) or 'you have been blocked' in html.lower()}")
        except HTTPError as e:
            print(f"    HTTPError: {e.code} {e.reason}")
        except Exception as e:
            print(f"    Error: {e}")
    print()

    for name, url in EVENTS.items():
        print("=" * 70)
        print(f"EVENT: {name}")
        print(f"URL:   {url}")
        try:
            status, html = fetch(url)
        except HTTPError as e:
            print(f"  HTTPError: {e.code} {e.reason}")
            try:
                body = e.read().decode("utf-8", errors="replace")
                print(f"  Body (first 1000 chars): {body[:1000]}")
            except Exception:
                pass
            continue
        except URLError as e:
            print(f"  URLError: {e}")
            continue
        except Exception as e:
            print(f"  Unexpected error: {e}")
            continue

        print(f"  Status: {status}")
        print(f"  Length: {len(html)} chars")
        print(f"  Title:  {get_title(html)}")
        print(f"  Looks like bot-challenge page: {looks_like_challenge(html)}")

        blobs = find_json_blobs(html)
        print(f"  Embedded JSON blobs found: {len(blobs)}")
        for label, snippet in blobs[:3]:
            print(f"    [{label}] {snippet}")

        snippets = find_date_context(html, variants)
        print(f"  Occurrences near target date variants: {len(snippets)}")
        for s in snippets[:5]:
            print(f"    {s}")

        kw_counts = find_keyword_context(html)
        print(f"  Keyword hits: {kw_counts}")

        # Dump a chunk of raw HTML around the middle so we can see general structure
        mid = len(html) // 2
        print(f"  Raw HTML sample (middle 1500 chars):\n{html[mid:mid+1500]}")
        print()


if __name__ == "__main__":
    main()
