"""Named thresholds for the gold app (env-overridable, Malang style).

Every gate number lives here so a scan's behaviour can be audited from one
file. Override with GOLDAPP_* environment variables.
"""
import os


def _f(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _i(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


SYMBOL = "PAXGUSDT"
BINANCE_FAPI_BASE = os.environ.get("GOLDAPP_BINANCE_BASE", "https://www.binance.com")

# --- Hard gates (ported from Malang v2.4) -----------------------------------
MIN_STOP_ATR_MULT = _f("GOLDAPP_MIN_STOP_ATR_MULT", 1.2)   # stop >= 1.2 x ATR(1h)
TP1_MIN_R = _f("GOLDAPP_TP1_MIN_R", 0.8)                   # at worst fill
TP2_MIN_R = _f("GOLDAPP_TP2_MIN_R", 1.5)                   # at worst fill
FILL_EXPIRY_HOURS = _f("GOLDAPP_FILL_EXPIRY_HOURS", 6.0)   # fill-or-expire
MAX_OPEN_SIGNALS = _i("GOLDAPP_MAX_OPEN_SIGNALS", 2)       # one instrument: cap low
EVENT_BUFFER_MIN = _i("GOLDAPP_EVENT_BUFFER_MIN", 30)      # shield before/after events
TIMEOUT_HOURS = _f("GOLDAPP_TIMEOUT_HOURS", 24.0)          # open-signal timeout

# --- Sessions (JST, winter — see RESEARCH_AND_DESIGN.md §3) ------------------
# Signal-eligible window: London open through the London/NY overlap.
SESSION_START_HOUR_JST = 17
SESSION_START_MIN_JST = 0
SESSION_END_HOUR_JST = 1
SESSION_END_MIN_JST = 30
ASIAN_START_HOUR_JST = 9   # Asian range build: 09:00-17:00 JST
ASIAN_END_HOUR_JST = 17

SCAN_INTERVAL_MIN = _i("GOLDAPP_SCAN_INTERVAL_MIN", 15)

# --- Production service (gold_app/service.py) --------------------------------
PORT = _i("GOLDAPP_PORT", 8791)                    # dashboard HTTP port
HOST = os.environ.get("GOLDAPP_HOST", "0.0.0.0")   # dashboard bind address
DATA_DIR = os.environ.get("GOLDAPP_DATA_DIR", "")  # empty -> <app root>/data
