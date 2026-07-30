# rome-website-checker

Monitors two Colosseum "Full Experience" ticket pages on `ticketing.colosseo.it`
and emails a list of recipients as soon as August 7, 2026 availability opens up.
Runs every 30 minutes on GitHub Actions, routed through a residential proxy.

## Why this needs a residential proxy

The ticketing site (built on the MidaTicket platform) sits behind an Octofence
WAAP firewall that hard-blocks requests from datacenter/cloud IPs — including
GitHub-hosted Actions runners and the free/standard tiers of scraping services
— with a 403/429 before any application logic runs. Only genuine residential
IPs get through.

Instead of scraping page HTML, `monitor.py` calls the same internal AJAX
endpoint the site's own calendar widget uses (`/mtajax/calendars_month`, found
via the browser's Network tab), and sends it through a residential proxy.

The endpoint returns per-time-slot capacity for a given month:

```json
{"success": true, "data": [
  {"startDateTime": "2026-08-07T06:45:00Z", "capacity": 0, "originalCapacity": 25, ...},
  ...
]}
```

`capacity` is how many spots are currently bookable for that slot (`0` = sold
out). The script filters for August 7 slots and alerts when any slot's capacity
goes from 0 (or unset) to something positive.

## Setup

### 1. Get residential proxy credentials

Sign up with any residential proxy provider (IPRoyal, Webshare, Smartproxy /
Decodo, Bright Data, Oxylabs — several offer trials or low-cost entry tiers).

**The one requirement: it must be a _residential_ proxy.** Datacenter proxies
hit the same firewall block and will not work.

Volume needed is tiny — two small JSON requests every 30 minutes, well under
1 GB of bandwidth for the entire monitoring window — so the smallest available
plan is generally sufficient.

Your provider will give you a host, port, username, and password. Combine them
into a single URL:

```
http://USERNAME:PASSWORD@PROXY_HOST:PORT
```

### 2. Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions** and add:

| Secret name | Value |
|---|---|
| `PROXY_URL` | Your proxy URL in the format above |
| `EMAIL_SENDER` | Your Gmail address |
| `EMAIL_PASSWORD` | Your Gmail [App Password](https://myaccount.google.com/apppasswords) |
| `EMAIL_RECIPIENT` | Where alerts should be sent (comma-separate multiple addresses) |

> **Note:** Use a Gmail App Password, not your regular Gmail login password.

### 3. Test it

Go to the **Actions** tab → **Colosseum Ticketing Monitor** → **Run workflow**.
The log should report current Aug 7 availability for both events (likely 0
spots, unless it just opened up). A 403/429 in the log means the proxy isn't
routing through a residential IP.

## How it works

1. GitHub Actions runs `monitor.py` every 30 minutes (also triggerable
   manually or via `repository_dispatch`)
2. For each event, it POSTs to the calendar AJAX endpoint through the proxy,
   requesting August 2026 slot data
3. It filters for August 7 slots and sums currently-available capacity
4. If that total increased since the last check, it emails everyone in
   `EMAIL_RECIPIENT`
5. New state is committed to `state.json` so the next run can compare

## Alternative: self-hosted runner (no proxy cost)

If you'd rather not pay for a proxy, you can run the checks from your own
machine's residential connection instead:

1. Repo → **Settings → Actions → Runners → New self-hosted runner**, follow
   the setup commands for your OS
2. Install it as a background service (`./svc.sh install && ./svc.sh start`
   on macOS/Linux) so it survives reboots
3. In `.github/workflows/monitor.yml`, change `runs-on: ubuntu-latest` to
   `runs-on: self-hosted` and drop the `Set up Python` step
4. Leave `PROXY_URL` unset — the script connects directly when it's absent

Tradeoff: checks only fire while that machine is powered on, awake, and
online. If it sleeps, checks are silently skipped until it's back.

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

`page_id` is the MidaTicket internal event ID — find it by opening the event
page, opening DevTools → Network tab, filtering for `calendars_month`, and
reading the `page=` value from the request body.

## Changing the check frequency

Edit the cron expression in `.github/workflows/monitor.yml`:

```yaml
- cron: '*/30 * * * *'   # every 30 minutes (default)
- cron: '*/15 * * * *'   # every 15 minutes
- cron: '0 * * * *'      # once an hour
```

More frequent checks react faster but consume proxy bandwidth proportionally.

> GitHub Actions does not guarantee exact timing for scheduled workflows —
> runs may be delayed by a few minutes during high-traffic periods.

## After August 7

Disable the workflow from the **Actions** tab (or delete
`.github/workflows/monitor.yml`) and cancel the proxy plan.
