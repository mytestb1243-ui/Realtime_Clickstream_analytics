"""
PostgreSQL storage layer for the real end-to-end demo.

Table shapes are identical, column-for-column, to the original
simulator project's db_manager.py -- deliberately, so this plugs into
the *same* `realtime_analytics` database (and, if you already ran the
simulator against Postgres, the tables it already created) without any
migration, and the Power BI report you already built keeps working
unchanged -- it will just show real clicks instead of simulated ones.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Table, Column, String, Float, Integer, MetaData, create_engine, text

import config

metadata = MetaData()

raw_events = Table(
    "raw_events", metadata,
    Column("event_id", String(32), primary_key=True),
    Column("event_time", String(40), index=True),
    Column("session_id", String(20), index=True),
    Column("visitor_id", String(20), index=True),
    Column("visitor_type", String(20)),
    Column("event_type", String(20)),
    Column("page_name", String(100)),
    Column("page_category", String(50)),
    Column("referrer_source", String(30)),
    Column("device_type", String(20)),
    Column("browser", String(20)),
    Column("country", String(50)),
    Column("region", String(50)),
    Column("time_on_page_seconds", Float),
    Column("conversion_type", String(30)),
    Column("conversion_value", Float),
    Column("session_duration_seconds", Float),
    Column("pages_in_session", Integer),
)

traffic_timeseries = Table(
    "traffic_timeseries", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("window_start", String(40), index=True),
    Column("window_end", String(40)),
    Column("page_views", Integer),
    Column("clicks", Integer),
    Column("conversions", Integer),
    Column("conversion_value", Float),
    Column("sessions_last_1min", Integer),
    Column("active_sessions_last_5min", Integer),
    Column("unique_visitors_last_5min", Integer),
    Column("conversion_rate", Float),
    Column("avg_session_duration_seconds", Float),
    Column("bounce_rate", Float),
)

traffic_by_source = Table(
    "traffic_by_source", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("window_start", String(40), index=True),
    Column("referrer_source", String(30)),
    Column("sessions", Integer),
    Column("page_views", Integer),
)

traffic_by_device = Table(
    "traffic_by_device", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("window_start", String(40), index=True),
    Column("device_type", String(20)),
    Column("sessions", Integer),
    Column("page_views", Integer),
)

traffic_by_geo = Table(
    "traffic_by_geo", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("window_start", String(40), index=True),
    Column("region", String(50)),
    Column("country", String(50)),
    Column("sessions", Integer),
    Column("page_views", Integer),
)

traffic_by_page = Table(
    "traffic_by_page", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("window_start", String(40), index=True),
    Column("page_name", String(100)),
    Column("page_category", String(50)),
    Column("views", Integer),
    Column("avg_dwell_seconds", Float),
)

live_kpis = Table(
    "live_kpis", metadata,
    Column("metric", String(50), primary_key=True),
    Column("value", Float),
)

alerts = Table(
    "alerts", metadata,
    Column("alert_id", String(32), primary_key=True),
    Column("triggered_at", String(40), index=True),
    Column("metric", String(50)),
    Column("window_value", Float),
    Column("baseline_avg", Float),
    Column("z_score", Float),
    Column("severity", String(20)),
    Column("message", String(255)),
)

pipeline_status = Table(
    "pipeline_status", metadata,
    Column("key", String(50), primary_key=True),
    Column("value", String(100)),
)

_engine = None


def get_engine():
    global _engine
    if _engine is not None:
        return _engine
    c = config.POSTGRES_CONFIG
    url = (
        f"postgresql+psycopg2://{c['user']}:{c['password']}"
        f"@{c['host']}:{c['port']}/{c['database']}"
    )
    _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def init_db():
    engine = get_engine()
    metadata.create_all(engine)


def insert_events_raw(rows: list):
    """Insert plain dicts (as built by app.py from JSON) -- unlike the
    original project's insert_events(), this doesn't expect Event
    dataclass objects, since the Flask endpoint already has dicts."""
    if not rows:
        return
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(raw_events.insert(), rows)


def insert_timeseries_row(row: dict):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(traffic_timeseries.insert(), row)


def insert_rows(table: Table, rows: list):
    if not rows:
        return
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(table.insert(), rows)


def insert_alert(row: dict):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(alerts.insert(), row)


def replace_live_kpis(kpis: dict):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(live_kpis.delete())
        rows = [{"metric": k, "value": float(v)} for k, v in kpis.items()]
        if rows:
            conn.execute(live_kpis.insert(), rows)


def set_status(key: str, value):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(pipeline_status.delete().where(pipeline_status.c.key == key))
        conn.execute(pipeline_status.insert(), {"key": key, "value": str(value)})


_prune_counter = {"n": 0}


def prune_old_rows(retention_hours: int = 48):
    _prune_counter["n"] += 1
    if _prune_counter["n"] % 20 != 0:
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention_hours)).isoformat(timespec="seconds")
    engine = get_engine()
    with engine.begin() as conn:
        for table in (traffic_timeseries, traffic_by_source, traffic_by_device, traffic_by_page, traffic_by_geo):
            conn.execute(table.delete().where(table.c.window_start < cutoff))
        conn.execute(raw_events.delete().where(raw_events.c.event_time < cutoff))
