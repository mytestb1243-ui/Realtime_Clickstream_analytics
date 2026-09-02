"""
Flask backend for the real end-to-end demo.

- Serves the sample website (the website/ folder) at http://127.0.0.1:5000/
- Receives real events from tracker.js at POST /api/track and writes
  them straight into the raw_events table of your PostgreSQL database
- Starts the aggregator (aggregator.py) as a background thread, which
  keeps recomputing the same rolling KPIs/breakdowns the original
  simulator project computed -- so the Power BI report you already
  built keeps working, now showing real clicks instead of simulated ones

Run with:  python app.py
Then open: http://127.0.0.1:5000/  and click around.
"""
import threading
import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify

import config
import db_manager
from ua_parser import parse_device_type, parse_browser
from aggregator import run_aggregator_loop

app = Flask(__name__, static_folder="website", static_url_path="")


@app.route("/")
def home():
    return app.send_static_file("index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/track", methods=["POST"])
def track():
    data = request.get_json(silent=True) or {}
    user_agent = request.headers.get("User-Agent", "")

    row = {
        "event_id": uuid.uuid4().hex[:12],
        "event_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": str(data.get("session_id", ""))[:20],
        "visitor_id": str(data.get("visitor_id", ""))[:20],
        "visitor_type": str(data.get("visitor_type", "New"))[:20],
        "event_type": str(data.get("event_type", "page_view"))[:20],
        "page_name": str(data.get("page_name", ""))[:100],
        "page_category": str(data.get("page_category", ""))[:50],
        "referrer_source": str(data.get("referrer_source", "Direct"))[:30],
        "device_type": parse_device_type(user_agent),
        "browser": parse_browser(user_agent),
        # No real geolocation for a localhost demo -- see README for how
        # a production system would fill these in from the request IP.
        "country": "Unknown",
        "region": "Local",
        "time_on_page_seconds": float(data.get("time_on_page_seconds") or 0),
        "conversion_type": str(data.get("conversion_type", ""))[:30],
        "conversion_value": float(data.get("conversion_value") or 0),
        "session_duration_seconds": 0.0,
        "pages_in_session": 0,
    }

    db_manager.insert_events_raw([row])
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    db_manager.init_db()

    stop_event = threading.Event()
    aggregator_thread = threading.Thread(target=run_aggregator_loop, args=(stop_event,), daemon=True)
    aggregator_thread.start()

    print("Real end-to-end demo running.")
    print(f"  Website : http://{config.FLASK_HOST}:{config.FLASK_PORT}/")
    print(f"  Database: {config.POSTGRES_CONFIG['database']} @ {config.POSTGRES_CONFIG['host']}:{config.POSTGRES_CONFIG['port']}")
    print("  Open the website above in your browser and click around --")
    print("  every click is a real HTTP request into your PostgreSQL database.")
    print("  Press Ctrl+C to stop.\n")

    # use_reloader=False matters: Flask's debug reloader spawns a second
    # process that would also hit this __main__ block and start a second
    # aggregator thread, double-writing every aggregate.
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, use_reloader=False)
