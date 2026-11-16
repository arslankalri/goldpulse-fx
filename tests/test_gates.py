import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gold_app import engine
from gold_app.engine import Signal

EVENTS = [
    {"name": "FOMC decision", "start": "2026-12-09T19:00:00Z", "end": "2026-12-09T20:00:00Z"},
    {"name": "US CPI", "start": "2026-12-10T13:30:00Z", "end": "2026-12-10T14:30:00Z"},
]


def jst(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=engine.JST)


class TestSessionGate(unittest.TestCase):
    def test_london_evening_eligible(self):
        ok, _ = engine.session_eligible(jst(2026, 11, 16, 18, 0))   # Monday
        self.assertTrue(ok)

    def test_asian_session_blocked(self):
        ok, _ = engine.session_eligible(jst(2026, 11, 16, 12, 0))
        self.assertFalse(ok)

    def test_weekend_blocked(self):
        ok, why = engine.session_eligible(jst(2026, 11, 14, 18, 0))  # Saturday
        self.assertFalse(ok)
        self.assertIn("weekend", why)
        ok, _ = engine.session_eligible(jst(2026, 11, 15, 20, 0))    # Sunday
        self.assertFalse(ok)

    def test_friday_session_runs_past_midnight(self):
        ok, _ = engine.session_eligible(jst(2026, 11, 14, 0, 30))    # Sat 00:30 = Fri session
        self.assertTrue(ok)


class TestEventShield(unittest.TestCase):
    def test_cpi_shield(self):
        now = datetime(2026, 12, 10, 13, 15, tzinfo=timezone.utc)   # 15 min before
        self.assertEqual(engine.event_block(now, EVENTS), "US CPI")
        now = datetime(2026, 12, 10, 14, 45, tzinfo=timezone.utc)   # 15 min after end
        self.assertEqual(engine.event_block(now, EVENTS), "US CPI")

    def test_fomc_shield(self):
        now = datetime(2026, 12, 9, 19, 30, tzinfo=timezone.utc)
        self.assertEqual(engine.event_block(now, EVENTS), "FOMC decision")

    def test_clear_outside_buffer(self):
        now = datetime(2026, 12, 10, 12, 0, tzinfo=timezone.utc)    # 90 min before
        self.assertIsNone(engine.event_block(now, EVENTS))


class TestNoiseFloor(unittest.TestCase):
    def test_blocks_tight_stop(self):
        ok, _ = engine.check_noise_floor(10.0, atr_1h=10.0)          # needs >= 12
        self.assertFalse(ok)

    def test_passes_at_floor(self):
        ok, _ = engine.check_noise_floor(12.0, atr_1h=10.0)
        self.assertTrue(ok)


class TestGeometry(unittest.TestCase):
    def test_blocks_weak_tp1(self):
        sig = Signal("LONG", "test", 100.0, 101.0, 95.0, 104.0, 120.0, 130.0)
        ok, why = engine.check_geometry(sig)     # TP1 = 0.5R at worst fill
        self.assertFalse(ok)
        self.assertIn("TP1", why)

    def test_passes_good_geometry(self):
        sig = Signal("LONG", "test", 100.0, 101.0, 95.0, 106.0, 111.0, 125.0)
        ok, _ = engine.check_geometry(sig)       # TP1 0.83R, TP2 1.67R
        self.assertTrue(ok)


class TestSweepDetector(unittest.TestCase):
    def test_sweep_up_gives_short(self):
        def c(h, l, cl):
            return {"t": 0, "o": cl, "h": h, "l": l, "c": cl, "v": 1.0, "ct": 0}
        m15 = [c(99, 97, 98), c(99, 97, 98), c(102, 98, 99), c(100, 98, 99)]
        from gold_app.regime import RegimeSnapshot
        snap = RegimeSnapshot(bias="neutral", price=99.0)
        sig = engine.detect_london_sweep(m15, 100.0, 90.0, 2.0, snap)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.direction, "SHORT")
        ok, _ = engine.check_geometry(sig)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
