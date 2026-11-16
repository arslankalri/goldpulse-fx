import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gold_app.journal import Journal, scoreboard, track_record

T0 = 1_700_000_000_000
H = 3600 * 1000


def candle(t, h, l):
    return {"t": t, "o": l, "h": h, "l": l, "c": l, "v": 1.0, "ct": t}


def base_record():
    return {"symbol": "PAXGUSDT", "direction": "LONG", "setup": "test",
            "tier": "B", "entry_low": 100.0, "entry_high": 101.0, "stop": 95.0,
            "tp1": 105.0, "tp2": 110.0, "tp3": 120.0, "status": "PENDING",
            "created_ms": T0}


class TestMergeSave(unittest.TestCase):
    def test_append_never_loses_records(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "journal.json")
            Journal(path).append(base_record())
            # A second, independent writer instance must merge, not overwrite.
            rec2 = base_record()
            rec2["id"] = "second"
            Journal(path).append(rec2)
            records = Journal(path).load()
            self.assertEqual(len(records), 2)
            self.assertTrue(all(r["app_version"] for r in records))

    def test_scoreboard_counts(self):
        recs = [dict(base_record(), status="CLOSED", close_reason="SL", tp_hits=[]),
                dict(base_record(), status="CLOSED", close_reason="TP3",
                     tp_hits=["TP1", "TP2", "TP3"], filled_ms=T0)]
        sb = scoreboard(recs)
        self.assertEqual((sb["issued"], sb["sl"], sb["tp3"], sb["wins"], sb["losses"]),
                         (2, 1, 1, 1, 1))


class TestTracker(unittest.TestCase):
    def test_tp1_then_breakeven_stop(self):
        candles = [candle(T0, 102, 99),          # fill candle
                   candle(T0 + H, 106, 98),      # TP1 hit -> stop to entry (101)
                   candle(T0 + 2 * H, 103, 100.5)]  # dips to 100.5 -> BE stop hit
        rec = track_record(base_record(), candles)
        self.assertEqual(rec["status"], "CLOSED")
        self.assertEqual(rec["close_reason"], "BE_AFTER_TP1")
        self.assertEqual(rec["tp_hits"], ["TP1"])
        self.assertEqual(rec["entry_fill"], 101.0)   # worst fill

    def test_sl_before_tp(self):
        candles = [candle(T0, 102, 99), candle(T0 + H, 103, 94)]
        rec = track_record(base_record(), candles)
        self.assertEqual(rec["status"], "CLOSED")
        self.assertEqual(rec["close_reason"], "SL")
        self.assertEqual(rec["tp_hits"], [])

    def test_same_candle_stop_wins_over_tp(self):
        # One candle touches both SL (95) and TP1 (105): stop counts first.
        candles = [candle(T0, 102, 99), candle(T0 + H, 106, 94)]
        rec = track_record(base_record(), candles)
        self.assertEqual(rec["close_reason"], "SL")
        self.assertEqual(rec["tp_hits"], [])

    def test_full_ladder(self):
        candles = [candle(T0, 102, 99), candle(T0 + H, 106, 100),
                   candle(T0 + 2 * H, 111, 102), candle(T0 + 3 * H, 121, 105)]
        rec = track_record(base_record(), candles)
        self.assertEqual(rec["close_reason"], "TP3")
        self.assertEqual(rec["tp_hits"], ["TP1", "TP2", "TP3"])

    def test_unfilled_expires(self):
        candles = [candle(T0 + i * H, 99, 90) for i in range(8)]  # never in zone
        rec = track_record(base_record(), candles)
        self.assertEqual(rec["status"], "EXPIRED")


if __name__ == "__main__":
    unittest.main()
