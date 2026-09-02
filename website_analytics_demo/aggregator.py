"""
The real-time processing core for the real end-to-end demo.

Unlike the original simulator project (which kept an in-memory buffer
fed by a queue, since one process generated and consumed events), here
events arrive as independent HTTP requests -- possibly from more than
one browser tab. So instead of an in-memory buffer, this background
thread re-reads the recent rows from PostgreSQL's raw_events table
every few seconds and recomputes the same rolling KPIs, breakdowns, and
anomaly check the original stream_processor.py did -- writing them into
the same output tables, so the Power BI report doesn't need to change
at all.
"""
import statistics
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

import config
import db_manager

_pageview_baseline = []


def _fetch_recent_events(seconds):
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    engine = db_manager.get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(db_manager.raw_events).where(db_manager.raw_events.c.event_time >= cutoff)
        ).mappings().all()
    return [dict(r) for r in rows]


def _session_stats(events, idle_timeout=None):
    """Group events by session_id. A session with no event in the last
    idle_timeout seconds is treated as finished, giving us a duration
    (first event to last event) and a page count -- the same
    inactivity-timeout idea real analytics tools use to decide a
    session is over, since a browser can't reliably tell us itself."""
    idle_timeout = idle_timeout or config.SESSION_IDLE_TIMEOUT_SECONDS
    by_session = defaultdict(list)
    for e in events:
        by_session[e["session_id"]].append(e)

    now = datetime.now(timezone.utc)
    finished = []
    for sid, evs in by_session.items():
        times = [datetime.fromisoformat(e["event_time"]) for e in evs]
        last_seen = max(times)
        if (now - last_seen).total_seconds() >= idle_timeout:
            duration = (max(times) - min(times)).total_seconds()
            pages = sum(1 for e in evs if e["event_type"] == "page_view")
            finished.append({"duration": duration, "pages": max(pages, 1)})
    return finished


def compute_and_store():
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    short = _fetch_recent_events(config.SHORT_WINDOW_SECONDS)
    long_ = _fetch_recent_events(config.LONG_WINDOW_SECONDS)

    page_views = [e for e in short if e["event_type"] == "page_view"]
    page_exits = [e for e in short if e["event_type"] == "page_exit"]   # dwell-time signal, see tracker.js
    clicks = [e for e in short if e["event_type"] == "click"]
    conversions = [e for e in short if e["event_type"] == "conversion"]

    active_sessions_5min = len({e["session_id"] for e in long_})
    unique_visitors_5min = len({e["visitor_id"] for e in long_})
    sessions_1min = len({e["session_id"] for e in short})

    conversion_value_sum = round(sum(e["conversion_value"] or 0 for e in conversions), 2)
    conversion_rate = round(len(conversions) / sessions_1min, 4) if sessions_1min else 0.0

    finished_sessions = _session_stats(long_)
    avg_session_duration = (
        round(statistics.mean([f["duration"] for f in finished_sessions]), 1) if finished_sessions else 0.0
    )
    bounce_rate = (
        round(len([f for f in finished_sessions if f["pages"] <= 1]) / len(finished_sessions), 4)
        if finished_sessions else 0.0
    )

    window_start = now_iso

    ts_row = {
        "window_start": window_start,
        "window_end": now_iso,
        "page_views": len(page_views),
        "clicks": len(clicks),
        "conversions": len(conversions),
        "conversion_value": conversion_value_sum,
        "sessions_last_1min": sessions_1min,
        "active_sessions_last_5min": active_sessions_5min,
        "unique_visitors_last_5min": unique_visitors_5min,
        "conversion_rate": conversion_rate,
        "avg_session_duration_seconds": avg_session_duration,
        "bounce_rate": bounce_rate,
    }
    db_manager.insert_timeseries_row(ts_row)

    _compute_breakdowns(page_views, page_exits, window_start)

    kpis = {
        "page_views_last_1min": len(page_views),
        "sessions_last_1min": sessions_1min,
        "active_sessions_last_5min": active_sessions_5min,
        "unique_visitors_last_5min": unique_visitors_5min,
        "conversions_last_1min": len(conversions),
        "conversion_value_last_1min": conversion_value_sum,
        "conversion_rate_last_1min": conversion_rate,
        "avg_session_duration_seconds": avg_session_duration,
        "bounce_rate_last_1min": bounce_rate,
    }
    db_manager.replace_live_kpis(kpis)
    db_manager.set_status("last_updated_at", now_iso)
    db_manager.set_status("pipeline_state", "running")
    db_manager.prune_old_rows()

    _check_anomaly(len(page_views), window_start)
    return kpis


def _compute_breakdowns(page_views, page_exits, window_start):
    source_totals = defaultdict(lambda: {"sessions": set(), "page_views": 0})
    device_totals = defaultdict(lambda: {"sessions": set(), "page_views": 0})
    geo_totals = defaultdict(lambda: {"sessions": set(), "page_views": 0})
    page_totals = defaultdict(lambda: {"views": 0, "total_dwell": 0.0, "dwell_samples": 0})

    for e in page_views:
        source_totals[e["referrer_source"]]["sessions"].add(e["session_id"])
        source_totals[e["referrer_source"]]["page_views"] += 1
        device_totals[e["device_type"]]["sessions"].add(e["session_id"])
        device_totals[e["device_type"]]["page_views"] += 1
        geo_totals[(e["region"], e["country"])]["sessions"].add(e["session_id"])
        geo_totals[(e["region"], e["country"])]["page_views"] += 1
        page_totals[(e["page_name"], e["page_category"])]["views"] += 1

    # Dwell time comes from page_exit events (see tracker.js), matched
    # by page, so a page's view count is never inflated by its own exit signal.
    for e in page_exits:
        key = (e["page_name"], e["page_category"])
        page_totals[key]["total_dwell"] += e["time_on_page_seconds"] or 0
        page_totals[key]["dwell_samples"] += 1

    source_rows = [
        {"window_start": window_start, "referrer_source": k, "sessions": len(v["sessions"]), "page_views": v["page_views"]}
        for k, v in source_totals.items()
    ]
    device_rows = [
        {"window_start": window_start, "device_type": k, "sessions": len(v["sessions"]), "page_views": v["page_views"]}
        for k, v in device_totals.items()
    ]
    geo_rows = [
        {"window_start": window_start, "region": r, "country": c, "sessions": len(v["sessions"]), "page_views": v["page_views"]}
        for (r, c), v in geo_totals.items()
    ]
    page_rows = [
        {
            "window_start": window_start, "page_name": p, "page_category": cat,
            "views": v["views"],
            "avg_dwell_seconds": round(v["total_dwell"] / v["dwell_samples"], 1) if v["dwell_samples"] else 0.0,
        }
        for (p, cat), v in page_totals.items()
    ]

    if source_rows:
        db_manager.insert_rows(db_manager.traffic_by_source, source_rows)
    if device_rows:
        db_manager.insert_rows(db_manager.traffic_by_device, device_rows)
    if geo_rows:
        db_manager.insert_rows(db_manager.traffic_by_geo, geo_rows)
    if page_rows:
        db_manager.insert_rows(db_manager.traffic_by_page, page_rows)


def _check_anomaly(page_view_count, window_start):
    global _pageview_baseline
    if len(_pageview_baseline) >= config.ANOMALY_MIN_SAMPLES:
        mean = statistics.mean(_pageview_baseline)
        stdev = statistics.pstdev(_pageview_baseline) or 1.0
        z = (page_view_count - mean) / stdev
        if abs(z) >= config.ANOMALY_Z_THRESHOLD:
            severity = "high" if abs(z) >= config.ANOMALY_Z_THRESHOLD * 1.5 else "medium"
            direction = "spike" if z > 0 else "drop"
            alert = {
                "alert_id": uuid.uuid4().hex[:12],
                "triggered_at": window_start,
                "metric": "page_views_last_1min",
                "window_value": float(page_view_count),
                "baseline_avg": round(mean, 2),
                "z_score": round(z, 2),
                "severity": severity,
                "message": (
                    f"Traffic {direction} detected: {page_view_count} page views "
                    f"vs baseline avg {mean:.1f} (z={z:.2f})"
                ),
            }
            db_manager.insert_alert(alert)
    _pageview_baseline.append(page_view_count)
    _pageview_baseline = _pageview_baseline[-30:]


def run_aggregator_loop(stop_event):
    db_manager.init_db()
    while not stop_event.is_set():
        try:
            compute_and_store()
        except Exception as exc:
            print(f"[aggregator] error: {exc}")
        stop_event.wait(config.PROCESS_TICK_SECONDS)
