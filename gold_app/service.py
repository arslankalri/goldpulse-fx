"""Production runner for the gold app (Oracle bot-server, next to Malang).

One process, two threads:
- scan loop: every GOLDAPP_SCAN_INTERVAL_MIN minutes — fetch PAXG data, run
  the tracker over open journal records, run one engine scan, journal any
  signal that passes EVERY gate, then rewrite dashboard/state.json.
- HTTP: stdlib ThreadingHTTPServer serving dashboard/ read-only on
  GOLDAPP_PORT (default 8791, GOLDAPP_HOST default 0.0.0.0), plus /healthz
  returning the app version and the last scan time.

Decision-support only: this process never places orders and holds no keys
or secrets. Clean SIGTERM/SIGINT shutdown for systemd.
"""
import json
import os
import signal
import sys
import threading
import traceback
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gold_app import __version__, config, data, engine, regime
from gold_app.journal import Journal, track_record
from gold_app.main import asian_range_today, build_state, session_vwap_now

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(ROOT, "dashboard")
STATE_PATH = os.path.join(DASHBOARD_DIR, "state.json")
EVENTS_PATH = os.path.join(ROOT, "events.json")

HEALTH = {"last_scan_at": None, "last_signal": None}


def data_dir():
    return config.DATA_DIR or os.path.join(ROOT, "data")


def journal_path():
    return os.path.join(data_dir(), "journal.json")


def log(msg):
    print(f"[gold-app {datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def write_state(state, path=STATE_PATH):
    """Atomic state.json write (temp file + rename), same shape as main.py."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def tick(now_utc=None, journal=None, state_path=STATE_PATH):
    """One track + scan cycle. Returns the state dict that was written."""
    now_utc = now_utc or datetime.now(timezone.utc)
    now_ms = int(now_utc.timestamp() * 1000)
    journal = journal or Journal(journal_path())
    records = journal.load()

    prem = data.premium_index()
    daily = data.klines(interval="1d", limit=120)
    h4 = data.klines(interval="4h", limit=120)
    h1 = data.klines(interval="1h", limit=120)
    m15 = data.klines(interval="15m", limit=300)

    # 1) Track open records against fresh candles; persist only if moved.
    tracked, changed = [], False
    for rec in records:
        new = track_record(rec, m15) if rec["status"] in ("PENDING", "OPEN") else rec
        if new != rec:
            changed = True
            log(f"tracker: {rec.get('id')} {rec['status']} -> {new['status']}"
                f" ({new.get('close_reason', '')})".rstrip(" ()"))
        tracked.append(new)
    if changed:
        journal.save_all(tracked)
        records = tracked

    # 2) Scan for a new signal (engine applies every hard gate).
    snap = regime.assess(daily, h4)
    now_jst = now_utc.astimezone(engine.JST)
    asian = asian_range_today(m15, now_jst)
    vwap = session_vwap_now(m15, now_jst)
    events = engine.load_events(EVENTS_PATH)
    open_count = sum(1 for r in records if r["status"] in ("PENDING", "OPEN"))
    result = engine.scan(now_utc, m15, h1, daily, snap, asian, vwap, events,
                         open_count=open_count)
    if result.signal is not None:
        rec = journal.append(result.signal.to_record(now_ms))
        records = journal.load()
        HEALTH["last_signal"] = rec["id"]
        log(f"NEW SIGNAL journaled: {rec['direction']} {rec['setup']} "
            f"[{rec['tier']}] id={rec['id']}")

    state = build_state(now_utc, prem, snap, result, records)
    write_state(state, state_path)
    HEALTH["last_scan_at"] = state["generated_at"]
    return state


def scan_loop(stop_event):
    while not stop_event.is_set():
        try:
            state = tick()
            sig = state["latest_scan"]["signal"]
            log("scan ok: " + (f"SIGNAL {sig['setup']} {sig['direction']}"
                               if sig else "no signal"))
        except Exception:
            log("scan FAILED (loop continues):\n" + traceback.format_exc())
        stop_event.wait(config.SCAN_INTERVAL_MIN * 60)


class _Handler(SimpleHTTPRequestHandler):
    health = HEALTH

    def do_GET(self):
        if self.path.split("?")[0] == "/healthz":
            body = json.dumps({
                "app": "gold-app", "version": __version__, "status": "ok",
                "last_scan_at": self.health.get("last_scan_at"),
                "last_signal": self.health.get("last_signal"),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self):
        if self.path.split("?")[0].endswith("state.json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write("http: %s\n" % (fmt % args))
        sys.stdout.flush()


def make_server(host, port, dashboard_dir=DASHBOARD_DIR, health=None):
    class Handler(_Handler):
        pass
    Handler.health = HEALTH if health is None else health
    server = ThreadingHTTPServer((host, port), partial(Handler, directory=dashboard_dir))
    server.daemon_threads = True
    return server


def main():
    stop = threading.Event()

    def _sig(signum, _frame):
        log(f"received signal {signum} — shutting down")
        stop.set()

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    server = make_server(config.HOST, config.PORT)
    http_thread = threading.Thread(target=server.serve_forever, daemon=True, name="http")
    http_thread.start()
    log(f"gold-app {__version__} up — dashboard http://{config.HOST}:{config.PORT}/"
        f" · journal {journal_path()} · scan every {config.SCAN_INTERVAL_MIN}m")
    scan_loop(stop)
    server.shutdown()
    server.server_close()
    log("shutdown complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
