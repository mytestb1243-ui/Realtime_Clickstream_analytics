-- Run this against the realtime_analytics database (in psql, pgAdmin's
-- Query Tool, or "SQL Shell (psql)") to clear out old simulated data
-- before starting a fresh, real click-tracking session.
--
-- psql:  \c realtime_analytics   then paste the line below.

TRUNCATE raw_events, traffic_timeseries, traffic_by_source, traffic_by_device,
         traffic_by_geo, traffic_by_page, live_kpis, alerts, pipeline_status;
