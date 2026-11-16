"""Append-only JSON journal + honest tracker (Malang semantics).

- Merge-save: append() re-reads the file and rewrites the full list via a
  temp file + atomic rename, so records are never lost to a stale writer.
- Records are stamped with the app version (era split by version).
- Tracker honesty: TP-before-SL sequencing candle by candle; if one candle
  touches both the stop and the next TP, the STOP is counted first
  (worst-case). TP/SL evaluation starts the candle AFTER the fill.
  After TP1, the stop moves to entry (bank TP1 -> stop to entry).
"""
import copy
import json
import os
import time

from . import __version__
from . import config

TP_LABELS = ["TP1", "TP2", "TP3"]


class Journal:
    def __init__(self, path):
        self.path = str(path)

    def load(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def append(self, record):
        records = self.load()                      # merge: never trust a cache
        rec = dict(record)
        rec.setdefault("id", f"{rec.get('created_ms', int(time.time() * 1000))}"
                             f"-{rec.get('symbol', 'PAXGUSDT')}-{rec.get('direction', '')}")
        rec["app_version"] = __version__
        records.append(rec)
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(records, f, indent=1)
        os.chmod(tmp, 0o644)
        os.replace(tmp, self.path)
        return rec

    def save_all(self, records):
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(records, f, indent=1)
        os.chmod(tmp, 0o644)
        os.replace(tmp, self.path)


def scoreboard(records):
    """Honest counts for the dashboard. Win = closed having reached TP1."""
    sb = {"issued": len(records), "filled": 0, "pending": 0, "open": 0,
          "tp1": 0, "tp2": 0, "tp3": 0, "sl": 0, "breakeven": 0,
          "expired": 0, "timeouts": 0, "resolved": 0, "wins": 0, "losses": 0,
          "era": __version__}
    for r in records:
        hits = r.get("tp_hits", [])
        if r.get("filled_ms"):
            sb["filled"] += 1
        if r["status"] == "PENDING":
            sb["pending"] += 1
        elif r["status"] == "OPEN":
            sb["open"] += 1
        elif r["status"] == "EXPIRED":
            sb["expired"] += 1
        if "TP1" in hits:
            sb["tp1"] += 1
        if "TP2" in hits:
            sb["tp2"] += 1
        if "TP3" in hits:
            sb["tp3"] += 1
        if r["status"] == "CLOSED":
            sb["resolved"] += 1
            reason = r.get("close_reason", "")
            if reason == "SL":
                sb["sl"] += 1
            if reason == "BE_AFTER_TP1":
                sb["breakeven"] += 1
            if reason == "TIMEOUT":
                sb["timeouts"] += 1
            if hits:
                sb["wins"] += 1
            elif reason == "SL":
                sb["losses"] += 1
    return sb


def track_record(record, candles):
    """Resolve one record against candles (dicts with t/h/l, time-ordered).

    Returns an updated copy; the input is not mutated.
    """
    rec = copy.deepcopy(record)
    if rec["status"] not in ("PENDING", "OPEN"):
        return rec
    created = rec["created_ms"]
    expiry_ms = created + config.FILL_EXPIRY_HOURS * 3600 * 1000
    relevant = [c for c in candles if c["t"] >= created]
    rec.setdefault("tp_hits", [])
    rec.setdefault("current_stop", rec["stop"])

    start_idx = 0
    if rec["status"] == "PENDING":
        filled_at = None
        for i, c in enumerate(relevant):
            if c["t"] > expiry_ms:
                break
            if c["l"] <= rec["entry_high"] and c["h"] >= rec["entry_low"]:
                filled_at = i
                break
        if filled_at is None:
            if relevant and relevant[-1]["t"] > expiry_ms:
                rec["status"] = "EXPIRED"
                rec["close_reason"] = "UNFILLED_6H"
            return rec
        rec["status"] = "OPEN"
        # Conservative grading: filled at the worst edge of the zone.
        rec["entry_fill"] = rec["entry_high"] if rec["direction"] == "LONG" else rec["entry_low"]
        rec["filled_ms"] = relevant[filled_at]["t"]
        start_idx = filled_at + 1        # TP/SL judged from the NEXT candle

    if rec["status"] == "OPEN":
        targets = [("TP1", rec["tp1"]), ("TP2", rec["tp2"]), ("TP3", rec["tp3"])]
        long = rec["direction"] == "LONG"
        timeout_ms = rec.get("filled_ms", created) + config.TIMEOUT_HOURS * 3600 * 1000
        for c in relevant[start_idx:]:
            stop = rec["current_stop"]
            sl_hit = c["l"] <= stop if long else c["h"] >= stop
            if sl_hit:                   # stop checked FIRST within a candle
                rec["status"] = "CLOSED"
                rec["close_reason"] = "BE_AFTER_TP1" if rec["tp_hits"] else "SL"
                rec["closed_ms"] = c["t"]
                return rec
            nxt = next(((lbl, px) for lbl, px in targets if lbl not in rec["tp_hits"]), None)
            if nxt:
                lbl, px = nxt
                tp_hit = c["h"] >= px if long else c["l"] <= px
                if tp_hit:
                    rec["tp_hits"].append(lbl)
                    if lbl == "TP1":
                        rec["current_stop"] = rec["entry_fill"]   # bank TP1 -> BE
                    if lbl == "TP3":
                        rec["status"] = "CLOSED"
                        rec["close_reason"] = "TP3"
                        rec["closed_ms"] = c["t"]
                        return rec
            if c["t"] > timeout_ms:
                rec["status"] = "CLOSED"
                rec["close_reason"] = "TIMEOUT"
                rec["closed_ms"] = c["t"]
                return rec
    return rec
