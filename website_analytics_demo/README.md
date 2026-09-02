# Real End-to-End Clickstream Demo

This is the "real data" companion to the `realtime_clickstream_analytics`
simulator. Instead of a Python process inventing fake visitors, this is
an actual website you open in a browser — every page view, click, and
conversion you generate is a real HTTP request that lands in your real
PostgreSQL database, seconds later.

It writes into the **same tables** the simulator used
(`raw_events`, `traffic_timeseries`, `traffic_by_source`,
`traffic_by_device`, `traffic_by_geo`, `traffic_by_page`, `live_kpis`,
`alerts`, `pipeline_status`), so the Power BI report you already built
against that database keeps working unchanged — it just starts showing
your real clicks instead of simulated ones.

## What's real here

- The website is a real set of HTML pages served by a real Flask server.
- Every page load, click, and "conversion" button press fires a real
  `fetch`/`sendBeacon` request from your browser to that server.
- The server writes each event straight into PostgreSQL — nothing is
  buffered in memory or faked.
- Device type and browser are parsed from your browser's *real*
  User-Agent string, not assigned randomly.
- Time-on-page is your *real* dwell time, measured from page load to
  when you navigate away or close the tab.
- Session length, bounce rate, and "active sessions" are inferred from
  real event timestamps using the same idle-timeout logic real
  analytics tools (like GA) use, since a browser can't announce "my
  session is over."

What's still fake, and why: the site itself ("Streamline") is a
fictional demo brand — it says so on every page — and pressing "Buy" or
"Sign up" does not charge a card or create an account, it just records
a `conversion` event so you have conversion data to build reports on.
Geolocation is hardcoded to `Unknown` / `Local` because this all runs on
your own machine (`localhost`), so there's no real visitor IP to look
up — see "Adding real geolocation" below if you want to take this
further.

## Requirements

- Python 3.9+
- PostgreSQL, already running locally with the `realtime_analytics`
  database created — the same one from the simulator project. If you
  never set that up, see that project's `POWERBI_SETUP.md` (Option B)
  first.
- A web browser.

## Quick start

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your database connection
copy .env.example .env       # Windows
cp .env.example .env         # macOS/Linux
# then open .env and fill in the SAME PostgreSQL password you used
# for the simulator project -- it's connecting to the same database.
```

**Before running this**, make sure the old simulator (`main.py` in the
other project) is **stopped**. Both projects write to the same
database, and running both at once will mix real and fake events
together in your report.

```bash
# 4. Run it
python app.py
```

You'll see a startup message confirming the website and database
connection. Now open **http://127.0.0.1:5000/** in your browser and
click around — browse pages, click buttons, try the signup form. Every
action is a real request hitting your database. Stop the server anytime
with Ctrl+C.

### Optional: start with a clean slate

If you ran the simulator before this, your tables already contain
simulated data. To clear it out so your report shows only real traffic
going forward, run `reset_data.sql` once against your database (in
`psql`, pgAdmin's Query Tool, or "SQL Shell (psql)"):

```sql
TRUNCATE raw_events, traffic_timeseries, traffic_by_source, traffic_by_device,
         traffic_by_geo, traffic_by_page, live_kpis, alerts, pipeline_status;
```

This is optional — the pipeline works fine either way, it's purely
about whether old fake rows show up alongside your real ones.

## Generating realistic traffic

A single browser tab clicking around is enough to prove the pipeline
works, but for a report that actually looks interesting, try to
generate some variety:

- Open the site in a few different browsers (Chrome, Firefox, Edge, or
  your phone) so `traffic_by_device` / `traffic_by_browser` aren't just
  one row.
- Try links with a `?utm_source=` parameter to control which traffic
  source an event is attributed to, e.g.
  `http://127.0.0.1:5000/?utm_source=social` or `?utm_source=email`.
  Without one, direct visits and your browser's real referrer (if any)
  are used.
- Click through to `/pricing.html` and press one of the plan buttons,
  or submit `/signup.html`, to generate `conversion` events with real
  dollar values.
- Leave a tab open for a while before closing it — that's a real,
  longer dwell time feeding `avg_dwell_seconds`.

## How it works

```
  your browser                          app.py (Flask)
  --------------                        ---------------------------
  tracker.js on every page   -- POST -->  /api/track
  sends page_view, click,      /api/track   writes one row straight
  conversion, page_exit                     into raw_events (Postgres)
  events as they happen                              |
                                                       v
                                          aggregator.py (background thread)
                                          every 5s: re-reads recent raw_events,
                                          recomputes rolling KPIs, breakdowns,
                                          session stats, z-score anomaly check
                                          -- same logic as the simulator's
                                          stream_processor.py, just re-read
                                          from the database instead of an
                                          in-memory queue
                                                       |
                                                       v
                                          traffic_timeseries, traffic_by_*,
                                          live_kpis, alerts (Postgres)
                                                       |
                                                       v
                                          Power BI (DirectQuery + Page Refresh)
                                          -- the report you already built
```

`tracker.js` tags every event with a `visitor_id` (persisted in
`localStorage`, so returning visits are recognized) and a `session_id`
(persisted in `sessionStorage`, so it resets when the tab/browser
closes). `app.py` never talks to the aggregation tables directly — it
only ever inserts into `raw_events`. `aggregator.py` is the only thing
that reads `raw_events` and writes the summary tables, exactly mirroring
what the simulator's `stream_processor.py` did, just pulling from
PostgreSQL each tick instead of an in-memory buffer (since events here
can arrive from more than one browser tab at once, there's no single
in-process queue to read from).

## Project structure

```
website_analytics_demo/
├── app.py               Flask server: serves the site, POST /api/track, starts the aggregator thread
├── aggregator.py         background thread: rolling KPIs/breakdowns/anomaly detection over Postgres
├── db_manager.py          PostgreSQL storage layer (SQLAlchemy) -- same schema as the simulator project
├── ua_parser.py           real User-Agent string -> device_type / browser
├── config.py              settings (env-var overridable via .env)
├── requirements.txt
├── .env.example           copy to .env -- reuse your simulator project's Postgres password
├── reset_data.sql          optional: clear old data before a fresh run
└── website/                the demo site
    ├── index.html, product.html, pricing.html, blog.html, signup.html
    ├── style.css
    └── tracker.js           fires real tracking events from the browser
```

## Connecting Power BI

No changes needed. If you already built a report against the
simulator's PostgreSQL database (DirectQuery + Page Refresh, per that
project's `POWERBI_SETUP.md`), it's reading from the same tables this
project writes into — just open it and keep working, or hit Refresh.
New real events will start appearing within one aggregator tick (5
seconds) of you clicking around the site.

## Adding real geolocation (optional, learning notes)

Since everything here runs on `localhost`, there's no real visitor IP
to geolocate — that's why `country`/`region` are hardcoded to
`Unknown`/`Local`. If you deployed this to a real server on the
internet, you'd fill those in from the request's IP address in
`app.py`'s `track()` function, e.g. with the free
[`ip-api.com`](https://ip-api.com) HTTP API or a local database like
MaxMind's GeoLite2, using `request.headers.get("X-Forwarded-For",
request.remote_addr)` as the IP to look up.

## Troubleshooting

- **"connection refused" / can't connect to PostgreSQL**: make sure
  PostgreSQL is actually running, and that `.env` has the right
  host/port/password.
- **Address already in use (port 5000)**: something else is using port
  5000 (on macOS this is often AirPlay Receiver). Set `FLASK_PORT` in
  `.env` to something else, like `5050`.
- **Your Power BI report shows old simulated numbers mixed with new
  real ones**: run `reset_data.sql` (see above), then generate some
  fresh traffic.
- **Numbers aren't updating in Power BI**: this project doesn't change
  how Power BI refreshes — it's the same DirectQuery + Page Refresh
  setup from `POWERBI_SETUP.md`. Manual Import-mode reports still need
  you to click Refresh.
- **`psycopg2` install fails on Windows**: use the prebuilt wheel,
  which `requirements.txt` already specifies
  (`psycopg2-binary`) — if it still fails, make sure you're on a
  64-bit Python and try `pip install --upgrade pip` first.
- **Nothing happens when I click buttons**: open your browser's
  DevTools console (F12) and check for errors — most commonly this
  means `app.py` isn't running, or `FLASK_PORT` in `.env` doesn't match
  the URL you opened.
