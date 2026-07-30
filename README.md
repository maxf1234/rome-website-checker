# Consulate Appointment Monitor

Watches the **Consulado-Geral de Portugal em Newark** booking page and emails
as soon as *any* appointment slot opens up.

**Appointment type monitored:** *Pedido da Nacionalidade Portuguesa para Filhos
de Cidadãos Portugueses | Application for Portuguese Nationality for Children
of Portuguese Citizens*

Booking page:
https://app.acuityscheduling.com/schedule/ce551904/appointment/71567018/calendar/11158185

> Note: the repo is still named `rome-website-checker` from an earlier project.
> The contents now monitor the consulate booking page instead.

## How it works

The booking page is a Squarespace Scheduling (Acuity) React app, so there's no
HTML to scrape — availability comes from a JSON API. The exact call and its
auth headers were captured by loading the real page in a headless browser and
recording its network traffic:

```
GET https://app.acuityscheduling.com/api/scheduling/v1/availability/month
    ?owner=ce551904
    &appointmentTypeId=71567018
    &calendarId=11158185
    &timezone=America/New_York
    &month=YYYY-MM-DD
headers:
    x-secondo-owner:   ce551904
    x-secondo-session: <client-generated UUID>
```

The response maps date → truthy when that date has availability. The app itself
computes available dates as `Object.keys(resp).filter(k => resp[k])`, and
`monitor.py` uses the same rule. An empty `{}` means nothing is open — which is
the normal state for this consulate.

Quirks worth knowing:
- `month` must be a full `YYYY-MM-DD` date. `YYYY-MM` is rejected with a
  misleading "must not be before the current month" error.
- The month requested must not be before the current month.
- `x-secondo-session` is just a client-generated UUID, so the script mints its
  own — no login or real session is required.

Every run scans the current month plus 6 months ahead.

## Setup

### GitHub Secrets

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `EMAIL_SENDER` | Gmail address alerts are sent *from* |
| `EMAIL_PASSWORD` | Gmail [App Password](https://myaccount.google.com/apppasswords) (not your normal password) |
| `EMAIL_RECIPIENT` | Where alerts go — comma-separate for multiple addresses |

### Schedule

Runs every 10 minutes via GitHub Actions (`.github/workflows/monitor.yml`):

```yaml
- cron: '*/10 * * * *'
```

Checks run on GitHub's servers — no proxy and no machine of your own needed,
since this site doesn't block datacenter IPs.

You can also trigger a run manually: **Actions → Acuity Availability Monitor →
Run workflow**.

## Alerting behavior

- Emails only when a date appears that wasn't available on the previous check,
  so you won't get repeat alerts for the same open slot.
- `state.json` holds the last known set of available dates and is committed
  back to the repo after each run.
- If requests fail *and* nothing is found, the run is treated as inconclusive
  and state is left untouched — so a transient outage can't cause a false
  "new availability" alert on the next successful run.

## Changing what's monitored

Edit the constants at the top of `monitor.py`:

```python
SLUG                = "ce551904"    # owner key from the booking URL
APPOINTMENT_TYPE_ID = "71567018"    # /appointment/<id>/
CALENDAR_ID         = "11158185"    # /calendar/<id>
TIMEZONE            = "America/New_York"
MONTHS_AHEAD        = 6
```

To monitor a *different* appointment type, open its booking page and read the
IDs straight out of the URL.

## Checking more often

Edit the cron in `.github/workflows/monitor.yml`. There's no per-request cost,
so the practical floor is GitHub's scheduling granularity:

```yaml
- cron: '*/5 * * * *'    # every 5 minutes
- cron: '*/10 * * * *'   # every 10 minutes (default)
```

> GitHub does not guarantee exact timing for scheduled workflows — runs can be
> delayed several minutes during busy periods, and scheduled workflows are
> disabled automatically after 60 days of repository inactivity.
