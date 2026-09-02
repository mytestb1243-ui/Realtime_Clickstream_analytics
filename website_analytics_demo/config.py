"""
Configuration for the real end-to-end demo. Reads the same PG_* variable
names as the original simulator project's .env, on purpose -- point this
at the same `realtime_analytics` PostgreSQL database and everything
(tables, Power BI report) keeps working unchanged.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent

POSTGRES_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": os.getenv("PG_PORT", "5432"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "postgres"),
    "database": os.getenv("PG_DATABASE", "realtime_analytics"),
}

# ---- Aggregation (same meaning as the original project's config.py) ----
PROCESS_TICK_SECONDS = 5
SHORT_WINDOW_SECONDS = 60
LONG_WINDOW_SECONDS = 300
SESSION_IDLE_TIMEOUT_SECONDS = 90   # no event for this long -> treat the session as finished, for duration/bounce stats
ANOMALY_MIN_SAMPLES = 6
ANOMALY_Z_THRESHOLD = 2.5

# ---- Flask ----
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")   # 127.0.0.1 = only this computer can reach it
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
