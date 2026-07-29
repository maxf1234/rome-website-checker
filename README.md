# rome-website-checker

Monitors two Colosseum "Full Experience" ticket pages on `ticketing.colosseo.it`
and emails a list of recipients as soon as August 7, 2026 availability opens up.
Runs for free on GitHub Actions every 30 minutes — no server needed.

## Why this isn't a simple page-scraper

The ticketing site (built on the MidaTicket platform) sits behind an Octofence
WAAP firewall that hard-blocks requests from datacenter/cloud IPs — including
GitHub Actions runners — with a 403/429 before any application logic runs.
Instead of scraping the page HTML, `monitor.py` calls the same internal AJAX
endpoint the site's own calendar widget uses (`/mtajax/calendars_month`,
found via the browser's Network tab), and routes that request through
[ScraperAPI](https://www.scraperapi.com/) so it comes from a residential IP
instead of GitHub's.

The endpoint returns per-time-slot capacity for a given month:

```json
{"success": true, "data": [
  {"startDateTime": "2026-08-07T06:45:00Z", "capacity": 0, "originalCapacity": 25, ...},
  ...
]}
```

`capacity` is how many spots are currently bookable for that slot (`0` = sold
out). The script filters for August 7 slots and alerts when any slot's
capacity goes from 0 (or unset) to something positive.

## Setup

### 1. Get a ScraperAPI key

Sign up free at [scraperapi.com](https://www.scraperapi.com/) — the free
tier (1,000 requests/month) comfortably covers checking 2 events every
30 minutes until August 7.

### 2. Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions** and add:

| Secret name | Value |
|---|---|
| `SCRAPER_API_KEY` | Your ScraperAPI key |
| `EMAIL_SENDER` | Your Gmail address |
| `EMAIL_PASSWORD` | Your Gmail [App Password](https://myaccount.google.com/apppasswords) |
| `EMAIL_RECIPIENT` | Where alerts should be sent (comma-separate multiple addresses) |

> **Note:** Use a Gmail App Password, not your regular Gmail login password.

### 3. Test it

Go to the **Actions** tab → **Colosseum Ticketing Monitor** → **Run workflow**.
Check the run's log output to confirm it found both events and reported
current Aug 7 availability (should be 0 spots on both, unless it just opened up).

## How it works

1. GitHub Actions runs `monitor.py` every 30 minutes (and can be triggered
   manually or via `repository_dispatch`)
2. For each event page, it POSTs to the site's calendar AJAX endpoint
   (via ScraperAPI) asking for August 2026 slot data
3. It filters for August 7 slots and sums up currently-available capacity
4. If that total increased from the last check (i.e., new availability
   appeared), it emails everyone in `EMAIL_RECIPIENT`
5. The new state is committed back to `state.json` so the next run can compare

## Changing the target date or events

Edit the constants at the top of `monitor.py`:

```python
EVENTS = {
    "Full Experience - Sotterranei e Arena": {"page_id": "225", "page_url": "..."},
    "Full Experience - Percorso Didattico":   {"page_id": "753", "page_url": "..."},
}
TARGET_DATE  = "2026-08-07"
TARGET_YEAR  = 2026
TARGET_MONTH = 8
```

`page_id` is the MidaTicket internal page/event ID — find it by opening the
event page, opening DevTools → Network tab, filtering for `calendars_month`,
and reading the `page=` value from the request body.

## Changing the check frequency

Edit the cron expression in `.github/workflows/monitor.yml`:

```yaml
- cron: '*/30 * * * *'   # every 30 minutes (default)
- cron: '*/15 * * * *'   # every 15 minutes (uses ~2x more ScraperAPI credits)
- cron: '0 * * * *'      # once an hour
```

> GitHub Actions does not guarantee exact timing for scheduled workflows —
> runs may be delayed by a few minutes during high-traffic periods.

## After August 7

Once the target date has passed (or you've booked), disable the workflow
from the **Actions** tab, or delete `.github/workflows/monitor.yml`, to stop
using ScraperAPI credits.
