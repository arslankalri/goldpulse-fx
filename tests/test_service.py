"""Tests for gold_app.service: state writer, tick integration, HTTP layer."""
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timezone
from unittest import mock

from gold_app import service
from gold_app.journal import Journal

BASE_MS = int(datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
NOW_UTC = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)  # 12:00 JST, Asian session


def candle(t, o, h, l, c):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": 1.0, "ct": t + 899_999}


def flat_series(limit, start_ms=BASE_MS - 120 * 3_600_000):
    out = []
    for i in range(limit):
        p = 100.0 + ((i * 7) % 13) * 0.05
        out.append(candle(start_ms + i * 3_600_000, p, p + 0.3, p - 0.3, p + 0.1))
    return out


class FakeData:
    def __init__(self, m15):
        self._m15 = m15

    def premium_index(self):
        return {"mark": 100.0, "index": 100.0, "funding": 0.0, "time": BASE_MS}

    def klines(self, interval="1h", limit=100):
        if interval == "15m":
            return self._m15
        return flat_series(limit)


class WriteStateTest(unittest.TestCase):
    def test_atomic_write_and_schema(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            service.write_state({"app": "gold-app", "version": "x", "scoreboard": {}}, path)
            self.assertFalse(os.path.exists(path + ".tmp"))
            with open(path) as f:
                got = json.load(f)
            self.assertEqual(got["app"], "gold-app")


class TickIntegrationTest(unittest.TestCase):
    def test_tick_tracks_open_record_and_writes_state(self):
        # PENDING long: fills on c1, then TP1/TP2/TP3 on the following candles.
        m15 = [
            candle(BASE_MS + 900_000, 100, 101.5, 99.5, 101),    # fill (zone 100-101)
            candle(BASE_MS + 1_800_000, 101, 103.0, 100.5, 102),  # TP1 102.5
            candle(BASE_MS + 2_700_000, 102, 104.0, 101.5, 103),  # TP2 103.5
            candle(BASE_MS + 3_600_000, 103, 106.0, 102.0, 105),  # TP3 105 -> CLOSED
        ]
        record = {
            "symbol": "PAXGUSDT", "direction": "LONG", "setup": "test",
            "tier": "B", "entry_low": 100.0, "entry_high": 101.0,
            "stop": 99.0, "tp1": 102.5, "tp2": 103.5, "tp3": 105.0,
            "status": "PENDING", "created_ms": BASE_MS,
            "tp_hits": [], "current_stop": 99.0,
        }
        with tempfile.TemporaryDirectory() as d:
            journal = Journal(os.path.join(d, "journal.json"))
            journal.append(record)
            state_path = os.path.join(d, "state.json")
            fake = FakeData(m15)
            with mock.patch.object(service, "data", fake):
                state = service.tick(now_utc=NOW_UTC, journal=journal,
                                     state_path=state_path)
            # Asian session -> engine must not issue anything.
            self.assertIsNone(state["latest_scan"]["signal"])
            # Tracker resolved the seeded record through the full ladder.
            saved = journal.load()
            self.assertEqual(len(saved), 1)
            rec = saved[0]
            self.assertEqual(rec["status"], "CLOSED")
            self.assertEqual(rec["close_reason"], "TP3")
            self.assertEqual(rec["tp_hits"], ["TP1", "TP2", "TP3"])
            self.assertEqual(rec["entry_fill"], 101.0)  # worst fill for a long
            # Scoreboard in state reflects the resolution honestly.
            sb = state["scoreboard"]
            self.assertEqual((sb["resolved"], sb["wins"], sb["tp3"]), (1, 1, 1))
            # state.json on disk parses and carries the dashboard schema keys.
            with open(state_path) as f:
                on_disk = json.load(f)
            for key in ("app", "version", "market", "regime", "latest_scan",
                        "open_signals", "scoreboard"):
                self.assertIn(key, on_disk)


class HttpTest(unittest.TestCase):
    def test_healthz_and_static_files(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "index.html"), "w") as f:
                f.write("<h1>gold dashboard</h1>")
            with open(os.path.join(d, "state.json"), "w") as f:
                json.dump({"ok": True}, f)
            health = {"last_scan_at": "2026-11-16T03:00:00+00:00", "last_signal": None}
            srv = service.make_server("127.0.0.1", 0, dashboard_dir=d, health=health)
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                port = srv.server_address[1]
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz",
                                            timeout=5) as r:
                    body = json.loads(r.read())
                self.assertEqual(body["status"], "ok")
                self.assertEqual(body["version"], service.__version__)
                self.assertEqual(body["last_scan_at"], "2026-11-16T03:00:00+00:00")
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/",
                                            timeout=5) as r:
                    self.assertIn("gold dashboard", r.read().decode())
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/state.json",
                                            timeout=5) as r:
                    self.assertEqual(json.loads(r.read()), {"ok": True})
            finally:
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
