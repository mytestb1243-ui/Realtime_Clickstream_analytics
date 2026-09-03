# Real-Time Clickstream Analytics — End-to-End Demo 1

> A working analytics pipeline you can watch happen: click a button in your
> browser and see the number move in your database seconds later.

<p>
  <img alt="Python"     src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img alt="Flask"      src="https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-13%2B-4169E1?logo=postgresql&logoColor=white">
  <img alt="SQLAlchemy" src="https://img.shields.io/badge/SQLAlchemy-2.x-D71F00">
  <img alt="Power BI"   src="https://img.shields.io/badge/Power%20BI-ready-F2C811?logo=powerbi&logoColor=black">
</p>

---

## What this is

Most analytics tutorials fake their data with a script that invents random
visitors. **This one doesn't.** It's a real (if small) website served by
Flask, and *every* page view, click, and conversion you make in the browser
is a genuine HTTP request that lands in a real PostgreSQL database, where a
background worker rolls it up into live KPIs — the same way Google Analytics,
Mixpanel, or Segment work under the hood.

It's the "real data" companion to a separate traffic **simulator** project.
It writes into the **exact same tables**, so any Power BI report built
against the simulator keeps working unchanged — it just starts showing your
real clicks instead of generated ones.

### What's genuinely real

| Thing | How it's real |
|---|---|
| **Events** | Every page load / click / conversion fires a real `fetch` / `sendBeacon` to the server |
| **Storage** | Each event is written straight to PostgreSQL — nothing buffered in memory or mocked |
| **Device & browser** | Parsed from your browser's actual `User-Agent` header |
| **Time on page** | Your real dwell time, measured from page load to when you leave the tab |
| **Sessions & bounce rate** | Inferred from real event timestamps using the same idle-timeout logic GA uses |

### What's intentionally fake

- **The website itself** — "Streamline" is a fictional demo brand (it says so
  on every page). Pressing *Buy* or *Sign up* records a `conversion` event so
  you have conversion data to chart; it doesn't charge a card or create an account.
- **Geolocation** — hardcoded to `Unknown` / `Local` because this runs on
  `localhost`, where there's no real visitor IP to look up. See
  [Adding real geolocation](#adding-real-geolocation) for how a deployed
  version would fill it in.

---

## Architecture

```
  YOUR BROWSER                              app.py  (Flask)
  ───────────────────                       ─────────────────────────────────
  tracker.js on every page  ──── POST ────▶  /api/track
    page_view / click /        (fetch or       one parameterised INSERT
    conversion / page_exit      sendBeacon)     into  raw_events  (Postgres)
                                                        │
                                                        ▼
                                             aggregator.py  (background thread)
                                             every 5s:
                                               • re-reads recent raw_events
                                               • recomputes rolling KPIs,
                                                 per-source/device/geo/page
                                                 breakdowns, session stats
                                               • z-score anomaly check
                                                        │
                                                        ▼
                                             traffic_timeseries, traffic_by_*,
                                             live_kpis, alerts, pipeline_status
                                                        │
                                                        ▼
                                             Power BI  (DirectQuery + auto-refresh)
```

**The golden rule:** `app.py` *only ever* inserts into `raw_events`.
`aggregator.py` is the *only* thing that reads `raw_events` and writes the
summary tables. Clean separation between ingestion and processing — and the
reason events can arrive from several browser tabs at once without stepping
on each other.

---

## Highlights

- **Genuine end-to-end pipeline** — browser → HTTP → Postgres → aggregation →
  BI, with no simulated step anywhere.
- **Real session logic** — bounce rate and session duration derived with the
  same inactivity-timeout heuristic real analytics tools use (a browser can't
  reliably announce "my session is over").
- **Anomaly detection** — rolling z-score check on page-view volume writes
  `spike` / `drop` alerts to an `alerts` table.
- **Beacon-based dwell tracking** — `navigator.sendBeacon` fires the exit
  event even as the tab is closing, so time-on-page isn't lost.
- **UTM + referrer attribution** — `?utm_source=` overrides; otherwise the
  real `document.referrer` is classified into Direct / Organic / Social / Referral.
- **Drop-in schema** — identical, column-for-column, to the simulator project,
  so existing Power BI reports need zero changes.
- **Dependency-light** — Flask, SQLAlchemy, psycopg2, python-dotenv. That's it.

---

## Tech stack

| Layer | Choice |
|---|---|
| Web server | **Flask** — serves the static site *and* the `/api/track` endpoint |
| Storage | **PostgreSQL** via **SQLAlchemy Core** (parameterised inserts, connection pooling) |
| Processing | Plain Python background **thread** on a 5-second tick |
| Front-end tracking | ~130 lines of vanilla JS (`tracker.js`) — no framework |
| Reporting | **Power BI** (DirectQuery + Page Refresh) |

---

## Project structure

```
website_analytics_demo/
├── app.py             Flask server: serves the site, POST /api/track, starts the aggregator thread
├── aggregator.py      Background thread: rolling KPIs / breakdowns / anomaly detection over Postgres
├── db_manager.py      PostgreSQL storage layer (SQLAlchemy) — schema shared with the simulator project
├── ua_parser.py       Real User-Agent string → device_type / browser
├── config.py          Settings (env-var overridable via .env)
├── requirements.txt
├── .env.example       Copy to .env and fill in your Postgres details
├── reset_data.sql     Optional: clear old data before a fresh run
└── website/           The demo site
    ├── index.html  product.html  pricing.html  blog.html  signup.html
    ├── style.css
    └── tracker.js     Fires the real tracking events from the browser
```

---

## Getting started

### Prerequisites

- **Python 3.9+**
- **PostgreSQL** running locally with a database created (default name:
  `realtime_analytics`). If you have the simulator project, point this at the
  same database.
- A web browser.

### Setup

```bash
# 1. Clone
git clone https://github.com/<your-username>/website_analytics_demo.git
cd website_analytics_demo

# 2. Virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

# 3. Dependencies
pip install -r requirements.txt

# 4. Configure the database connection
copy .env.example .env          # Windows
cp .env.example .env            # macOS / Linux
#   then edit .env with your PostgreSQL host / user / password
```

### Run

```bash
python app.py
```

You'll see a startup banner confirming the website URL and database. Open
**http://127.0.0.1:5000/** and click around — browse pages, press the plan
buttons, submit the signup form. Every action is a real request hitting your
database. `Ctrl+C` to stop.

> **If you also have the simulator project:** stop it first. Both write to the
> same database, and running both at once mixes real and generated events.

### Optional — start from a clean slate

If old data is already in your tables, clear it once (in `psql`, pgAdmin, or
the SQL Shell):

```sql
\c realtime_analytics
TRUNCATE raw_events, traffic_timeseries, traffic_by_source, traffic_by_device,
         traffic_by_geo, traffic_by_page, live_kpis, alerts, pipeline_status;
```

This is purely cosmetic — the pipeline works either way.

---

## Generating interesting traffic

One tab clicking around proves the pipeline works, but for a report worth
looking at, add some variety:

- **Multiple browsers / your phone** — so `traffic_by_device` and
  `traffic_by_browser` aren't a single row.
- **UTM tags** — `http://127.0.0.1:5000/?utm_source=social` or
  `?utm_source=email` to control the attributed traffic source.
- **Conversions** — press a plan button on `/pricing.html` or submit
  `/signup.html` to generate `conversion` events with real dollar values.
- **Dwell time** — leave a tab open a while before closing it; that's a real,
  longer reading feeding `avg_dwell_seconds`.

---

## Data model

| Table | Written by | Contents |
|---|---|---|
| `raw_events` | `app.py` only | One row per browser event (`page_view` / `click` / `conversion` / `page_exit`) |
| `traffic_timeseries` | aggregator — 1 row / tick | Rolling counts, conversion rate, session duration, bounce rate |
| `traffic_by_source` / `_device` / `_geo` / `_page` | aggregator — N rows / tick | Per-dimension rollups (+ dwell time for pages) |
| `live_kpis` | aggregator — full replace / tick | Current-snapshot `metric` → `value` pairs |
| `alerts` | aggregator — on anomaly | z-score traffic spike / drop alerts |
| `pipeline_status` | aggregator — upsert / tick | `last_updated_at`, `pipeline_state` |

### Key settings (`config.py`)

| Setting | Default | Meaning |
|---|---|---|
| `PROCESS_TICK_SECONDS` | `5` | How often the aggregator recomputes |
| `SHORT_WINDOW_SECONDS` | `60` | "Last 1 minute" rolling window |
| `LONG_WINDOW_SECONDS` | `300` | "Last 5 minutes" window (sessions, unique visitors) |
| `SESSION_IDLE_TIMEOUT_SECONDS` | `90` | No event for this long → session counts as finished |
| `ANOMALY_Z_THRESHOLD` | `2.5` | z-score past which an alert is written |

---

## How it works — the click's journey

1. **Page loads** → `tracker.js` resolves a `visitor_id` (`localStorage`,
   survives restarts → "Returning") and a `session_id` (`sessionStorage`,
   resets with the tab).
2. **`page_view` sent** immediately via `fetch`.
3. **You click a `[data-track]` element** → a delegated listener sends a
   `click`, or a `conversion` (with type + dollar value) if it also has
   `data-conversion`.
4. **You leave the tab** → `navigator.sendBeacon` sends `page_exit` with your
   real dwell time — a *separate* event type, so it never inflates view counts.
5. **`POST /api/track`** normalises the JSON, stamps a server-side UTC
   timestamp, derives device/browser from the `User-Agent`, and runs **one
   parameterised `INSERT`** into `raw_events`.
6. **Every 5 seconds** the aggregator `SELECT`s recent `raw_events`,
   recomputes KPIs / breakdowns / session stats / anomaly check in memory,
   and writes the summary tables.
7. **Power BI** reads those summary tables on DirectQuery + Page Refresh —
   new events appear within one tick.

---

## Connecting Power BI

No changes needed. If you already built a DirectQuery report against the
simulator's database, it reads from the same tables this project writes into.
Open it and hit Refresh — real events start appearing within ~5 seconds of
clicking around the site.

---

## Adding real geolocation

Everything here runs on `localhost`, so `country` / `region` are hardcoded to
`Unknown` / `Local`. On a deployed server you'd fill them in from the request
IP inside `app.py`'s `track()` function — using
`request.headers.get("X-Forwarded-For", request.remote_addr)` as the IP, and
looking it up with a free API like [ip-api.com](https://ip-api.com) or a
local database like MaxMind GeoLite2.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **"connection refused" / can't reach Postgres** | Make sure PostgreSQL is running and `.env` has the right host / port / password |
| **Address already in use (port 5000)** | Something else holds port 5000 (on macOS, often AirPlay Receiver). Set `FLASK_PORT=5050` in `.env` |
| **Old numbers mixed with new ones in Power BI** | Run the `TRUNCATE` from [clean slate](#optional--start-from-a-clean-slate), then generate fresh traffic |
| **Nothing happens when I click** | Open DevTools (F12) → Console. Usually `app.py` isn't running, or `FLASK_PORT` doesn't match the URL you opened |
| **`psycopg2` install fails on Windows** | `requirements.txt` already pins `psycopg2-binary`; make sure you're on 64-bit Python and run `pip install --upgrade pip` first |

---

## License

MIT — do whatever you like with it.
