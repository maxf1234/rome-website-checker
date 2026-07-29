# rome-website-checker

Monitors two Colosseum "Full Experience" ticket pages on `ticketing.colosseo.it`
and emails a list of recipients as soon as August 7, 2026 availability opens up.
Checks run every 30 minutes via GitHub Actions, on a self-hosted runner (your
own Mac) — see why below.

## Why this isn't a simple page-scraper, and why it needs your machine

The ticketing site (built on the MidaTicket platform) sits behind an Octofence
WAAP firewall that hard-blocks requests from datacenter/cloud IPs — including
GitHub-hosted Actions runners, and free/standard tiers of scraping proxy
services — with a 403/429 before any application logic runs. Only genuine
residential IPs get through.

Instead of scraping the page HTML, `monitor.py` calls the same internal AJAX
endpoint the site's own calendar widget uses (`/mtajax/calendars_month`,
found via the browser's Network tab). Since it needs a residential IP, the
workflow runs on a **self-hosted runner** — a small agent installed on your
own Mac — instead of GitHub's cloud runners.

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

### 1. Install the self-hosted runner on your Mac

1. Go to your repo → **Settings → Actions → Runners → New self-hosted runner**
2. Select **macOS** and your chip type (Apple Silicon = ARM64, Intel = x64)
3. GitHub shows a set of Terminal commands — copy and run them one by one in
   Terminal.app. They'll look roughly like:
   ```bash
   mkdir actions-runner && cd actions-runner
   curl -o actions-runner-osx.tar.gz -L https://github.com/actions/runner/releases/download/vX.X.X/actions-runner-osx-....tar.gz
   tar xzf ./actions-runner-osx.tar.gz
   ./config.sh --url https://github.com/maxf1234/rome-website-checker --token XXXXXXXX
   ```
   (Use the exact commands and token GitHub generates for you — they're
   unique per-repo and expire, so copy them fresh from the page.)
4. When `config.sh` asks questions, defaults are fine — just hit Enter.
5. **Install it as a background service** (so it keeps running after you
   close Terminal, and restarts on login/reboot):
   ```bash
   ./svc.sh install
   ./svc.sh start
   ```
6. Back on the GitHub Runners page, you should now see your runner listed
   with a green "Idle" status.

### 2. Confirm Python 3 is available

In Terminal, run:
```bash
python3 --version
```
If that errors, install Python 3 from [python.org](https://www.python.org/downloads/)
or via Homebrew (`brew install python3`).

### 3. Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions** and add:

| Secret name | Value |
|---|---|
| `EMAIL_SENDER` | Your Gmail address |
| `EMAIL_PASSWORD` | Your Gmail [App Password](https://myaccount.google.com/apppasswords) |
| `EMAIL_RECIPIENT` | Where alerts should be sent (comma-separate multiple addresses) |

> **Note:** Use a Gmail App Password, not your regular Gmail login password.

### 4. Test it

Go to the **Actions** tab → **Colosseum Ticketing Monitor** → **Run workflow**.
It should pick up your self-hosted runner (visible in the run's log as
"Runner name: ..." matching your machine) and report current Aug 7
availability for both events (likely 0 spots, unless it just opened up).

## How it works

1. GitHub Actions runs `monitor.py` on your Mac every 30 minutes (and can
   also be triggered manually or via `repository_dispatch`)
2. For each event page, it POSTs directly to the site's calendar AJAX
   endpoint asking for August 2026 slot data
3. It filters for August 7 slots and sums up currently-available capacity
4. If that total increased from the last check (i.e., new availability
   appeared), it emails everyone in `EMAIL_RECIPIENT`
5. The new state is committed back to `state.json` so the next run can compare

## Keeping your Mac available

Checks only fire while your Mac is on, awake, and connected to the internet
— if it's asleep or off when a scheduled check comes up, that check is
simply skipped (no error, just silence until the runner is back online).
To maximize uptime during the days you care about:
- In **System Settings → Battery/Energy Saver**, disable "Put hard disks to
  sleep" and consider disabling automatic sleep, or use "Prevent your Mac
  from sleeping automatically when the display is off"
- Keep it plugged in and connected to Wi-Fi/Ethernet

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
- cron: '*/15 * * * *'   # every 15 minutes
- cron: '0 * * * *'      # once an hour
```

Since checks now run on your own machine, there's no proxy-credit cost to
checking more frequently — the only cost is your Mac staying awake and
connected.

> GitHub Actions does not guarantee exact timing for scheduled workflows —
> runs may be delayed by a few minutes during high-traffic periods.

## After August 7

Once the target date has passed (or you've booked), you can:
- Disable the workflow from the **Actions** tab, and/or
- Stop and remove the runner: `./svc.sh stop && ./svc.sh uninstall` in the
  `actions-runner` folder, then remove it from Settings → Actions → Runners
