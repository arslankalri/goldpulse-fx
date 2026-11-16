"""Signal engine: three v0.1 setups behind Malang's hard gates.

Setups (RESEARCH_AND_DESIGN.md §7):
  1. london_sweep_reverse — London sweeps the Asian range extreme, closes
     back inside; enter against the sweep.
  2. overlap_vwap_pullback — trend-aligned pullback to session VWAP in the
     overlap, rejection candle.
  3. level_break_retest — prior-day / swing level breaks and the retest holds.

Hard gates (checked for every candidate, in order):
  session eligibility -> weekend block -> event shield -> open-signal cap
  -> ATR noise floor -> TP geometry at worst fill.
A candidate that fails a gate is dropped with the reason logged — a signal
must pass EVERY check or it does not exist.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import config, indicators

JST = timezone(timedelta(hours=9))
UTC = timezone.utc


@dataclass
class Signal:
    direction: str                 # "LONG" | "SHORT"
    setup: str
    entry_low: float
    entry_high: float
    stop: float
    tp1: float
    tp2: float
    tp3: float
    tier: str = "B"
    regime_bias: str = "neutral"
    counter_trend: bool = False
    reasons: list = field(default_factory=list)
    atr_1h: float = None
    symbol: str = config.SYMBOL

    @property
    def worst_fill(self):
        """Conservative fill: the zone edge furthest from the targets."""
        return self.entry_high if self.direction == "LONG" else self.entry_low

    @property
    def stop_distance(self):
        return abs(self.worst_fill - self.stop)

    def rr(self, target):
        d = self.stop_distance
        return abs(target - self.worst_fill) / d if d > 0 else 0.0

    def to_record(self, created_ms):
        return {
            "symbol": self.symbol, "direction": self.direction,
            "setup": self.setup, "tier": self.tier,
            "entry_low": self.entry_low, "entry_high": self.entry_high,
            "stop": self.stop, "tp1": self.tp1, "tp2": self.tp2, "tp3": self.tp3,
            "regime_bias": self.regime_bias, "counter_trend": self.counter_trend,
            "reasons": list(self.reasons), "atr_1h": self.atr_1h,
            "status": "PENDING", "created_ms": int(created_ms),
        }


@dataclass
class ScanResult:
    signal: Signal = None
    log: list = field(default_factory=list)   # every gate/detector verdict


# ---------------------------------------------------------------- gates ----

def session_eligible(now_jst):
    """Signal window 17:00-01:30 JST. The post-midnight segment belongs to
    the previous day's session, so the weekend check uses the effective
    session date (Fri 17:00 -> Sat 01:30 is Friday's session and eligible;
    Sat/Sun daytime is never eligible)."""
    t = now_jst
    minutes = t.hour * 60 + t.minute
    start = config.SESSION_START_HOUR_JST * 60 + config.SESSION_START_MIN_JST
    end = config.SESSION_END_HOUR_JST * 60 + config.SESSION_END_MIN_JST
    if minutes >= start:
        session_date = t.date()
    elif minutes <= end:
        session_date = (t - timedelta(days=1)).date()
    else:
        return False, "outside session window (17:00-01:30 JST)"
    if session_date.weekday() >= 5:
        return False, "weekend — PAXG unanchored while COMEX is closed"
    return True, "session window open"


def load_events(path):
    with open(path) as f:
        data = json.load(f)
    return data.get("events", data if isinstance(data, list) else [])


def _parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def event_block(now_utc, events, buffer_min=None):
    """Name of the event whose shield window contains `now`, else None."""
    buf = timedelta(minutes=config.EVENT_BUFFER_MIN if buffer_min is None else buffer_min)
    for ev in events:
        start = _parse_iso(ev["start"])
        end = _parse_iso(ev.get("end", ev["start"]))
        if start - buf <= now_utc <= end + buf:
            return ev.get("name", "event")
    return None


def check_noise_floor(stop_distance, atr_1h, mult=None):
    if atr_1h is None:
        return False, "no ATR(1h) available"
    need = (config.MIN_STOP_ATR_MULT if mult is None else mult) * atr_1h
    if stop_distance < need - 1e-9:   # epsilon: a stop widened to exactly the floor passes
        return False, f"stop {stop_distance:.2f} inside noise floor {need:.2f} (1.2x ATR1h)"
    return True, "noise floor ok"


def check_geometry(sig):
    if sig.rr(sig.tp1) < config.TP1_MIN_R:
        return False, f"TP1 only {sig.rr(sig.tp1):.2f}R at worst fill (< {config.TP1_MIN_R}R)"
    if sig.rr(sig.tp2) < config.TP2_MIN_R:
        return False, f"TP2 only {sig.rr(sig.tp2):.2f}R at worst fill (< {config.TP2_MIN_R}R)"
    return True, "geometry ok"


def _finish_stop(structural_stop, worst_fill, atr_1h):
    """Stop = structural level, widened to the noise floor if needed
    (widening is noted on the card — never silently)."""
    dist = abs(worst_fill - structural_stop)
    floor = config.MIN_STOP_ATR_MULT * atr_1h
    if dist >= floor:
        return structural_stop, None
    direction = 1 if structural_stop > worst_fill else -1
    return worst_fill + direction * floor, "stop widened to 1.2x ATR(1h) noise floor"


# ------------------------------------------------------------ detectors ----

def detect_london_sweep(m15, asian_high, asian_low, atr_1h, regime):
    if asian_high is None or asian_low is None or len(m15) < 4:
        return None
    mid = (asian_high + asian_low) / 2.0
    height = asian_high - asian_low
    for c in reversed(m15[-8:]):
        # Sweep up -> SHORT: wicked above Asian high, closed back inside.
        if c["h"] > asian_high and c["c"] < asian_high and m15[-1]["c"] < asian_high:
            entry_low = asian_high - 0.2 * atr_1h
            entry_high = asian_high + 0.05 * atr_1h
            stop, note = _finish_stop(c["h"] + 0.1 * atr_1h, entry_low, atr_1h)
            sig = Signal("SHORT", "london_sweep_reverse", entry_low, entry_high,
                         stop, mid, asian_low, asian_low - 0.5 * height,
                         atr_1h=atr_1h,
                         reasons=["London swept the Asian high and closed back inside"])
            if note:
                sig.reasons.append(note)
            return sig
        # Sweep down -> LONG.
        if c["l"] < asian_low and c["c"] > asian_low and m15[-1]["c"] > asian_low:
            entry_low = asian_low - 0.05 * atr_1h
            entry_high = asian_low + 0.2 * atr_1h
            stop, note = _finish_stop(c["l"] - 0.1 * atr_1h, entry_high, atr_1h)
            sig = Signal("LONG", "london_sweep_reverse", entry_low, entry_high,
                         stop, mid, asian_high, asian_high + 0.5 * height,
                         atr_1h=atr_1h,
                         reasons=["London swept the Asian low and closed back inside"])
            if note:
                sig.reasons.append(note)
            return sig
    return None


def detect_vwap_pullback(m15, vwap_now, atr_1h, regime, daily):
    if vwap_now is None or len(m15) < 6 or regime.bias == "neutral":
        return None
    direction = "LONG" if regime.bias == "bullish" else "SHORT"
    recent = m15[-4:]
    touched = any(abs(c["l"] - vwap_now) <= 0.3 * atr_1h if direction == "LONG"
                  else abs(c["h"] - vwap_now) <= 0.3 * atr_1h for c in recent)
    if not touched:
        return None
    last = m15[-1]
    body = abs(last["c"] - last["o"])
    if direction == "LONG":
        wick = min(last["o"], last["c"]) - last["l"]
        if not (last["c"] > last["o"] and wick >= body):
            return None
        entry_low, entry_high = vwap_now - 0.15 * atr_1h, vwap_now + 0.15 * atr_1h
        swing = min(c["l"] for c in m15[-8:])
        stop, note = _finish_stop(swing - 0.1 * atr_1h, entry_high, atr_1h)
        highs = [p for _, p in indicators.swing_highs(m15[-40:])]
        tp1 = max([h for h in highs if h > entry_high], default=entry_high + 1.0 * abs(entry_high - stop))
        pdh = indicators.prior_day_high_low(daily)
        tp2 = pdh[0] if pdh and pdh[0] > tp1 else entry_high + 1.8 * abs(entry_high - stop)
        tp3 = entry_high + 2.8 * abs(entry_high - stop)
    else:
        wick = last["h"] - max(last["o"], last["c"])
        if not (last["c"] < last["o"] and wick >= body):
            return None
        entry_low, entry_high = vwap_now - 0.15 * atr_1h, vwap_now + 0.15 * atr_1h
        swing = max(c["h"] for c in m15[-8:])
        stop, note = _finish_stop(swing + 0.1 * atr_1h, entry_low, atr_1h)
        lows = [p for _, p in indicators.swing_lows(m15[-40:])]
        tp1 = min([x for x in lows if x < entry_low], default=entry_low - 1.0 * abs(stop - entry_low))
        pdl = indicators.prior_day_high_low(daily)
        tp2 = pdl[1] if pdl and pdl[1] < tp1 else entry_low - 1.8 * abs(stop - entry_low)
        tp3 = entry_low - 2.8 * abs(stop - entry_low)
    sig = Signal(direction, "overlap_vwap_pullback", entry_low, entry_high,
                 stop, tp1, tp2, tp3, atr_1h=atr_1h,
                 reasons=[f"trend-aligned pullback to session VWAP with rejection candle"])
    if note:
        sig.reasons.append(note)
    return sig


def detect_break_retest(m15, daily, atr_1h, regime):
    pd = indicators.prior_day_high_low(daily)
    if pd is None or len(m15) < 10:
        return None
    pdh, pdl = pd
    closes = [c["c"] for c in m15]
    # LONG: a close above PDH, then a later candle retests PDH and holds.
    for i in range(2, len(m15) - 1):
        if closes[i] > pdh and all(closes[j] <= pdh for j in range(max(0, i - 6), i)):
            for c in m15[i + 1:]:
                if abs(c["l"] - pdh) <= 0.2 * atr_1h and c["c"] > pdh:
                    entry_low, entry_high = pdh, pdh + 0.2 * atr_1h
                    stop, note = _finish_stop(pdh - 0.25 * atr_1h, entry_high, atr_1h)
                    r = abs(entry_high - stop)
                    sig = Signal("LONG", "level_break_retest", entry_low, entry_high,
                                 stop, entry_high + 1.0 * r, entry_high + 1.8 * r,
                                 entry_high + 3.0 * r, atr_1h=atr_1h,
                                 reasons=["prior-day high broken, retest held (R-multiple targets)"])
                    if note:
                        sig.reasons.append(note)
                    return sig
            break
    for i in range(2, len(m15) - 1):
        if closes[i] < pdl and all(closes[j] >= pdl for j in range(max(0, i - 6), i)):
            for c in m15[i + 1:]:
                if abs(c["h"] - pdl) <= 0.2 * atr_1h and c["c"] < pdl:
                    entry_low, entry_high = pdl - 0.2 * atr_1h, pdl
                    stop, note = _finish_stop(pdl + 0.25 * atr_1h, entry_low, atr_1h)
                    r = abs(stop - entry_low)
                    sig = Signal("SHORT", "level_break_retest", entry_low, entry_high,
                                 stop, entry_low - 1.0 * r, entry_low - 1.8 * r,
                                 entry_low - 3.0 * r, atr_1h=atr_1h,
                                 reasons=["prior-day low broken, retest held (R-multiple targets)"])
                    if note:
                        sig.reasons.append(note)
                    return sig
            break
    return None


# ----------------------------------------------------------------- scan ----

def scan(now_utc, m15, h1, daily, regime, asian_range, vwap_now, events,
         open_count=0):
    """One scan. Returns ScanResult(signal|None, log of every verdict)."""
    log = []
    now_jst = now_utc.astimezone(JST)
    ok, why = session_eligible(now_jst)
    log.append(f"session: {why}")
    if not ok:
        return ScanResult(None, log)
    blocked = event_block(now_utc, events or [])
    if blocked:
        log.append(f"event shield: blocked by {blocked} (±{config.EVENT_BUFFER_MIN} min)")
        return ScanResult(None, log)
    log.append("event shield: clear")
    if open_count >= config.MAX_OPEN_SIGNALS:
        log.append(f"cap: {open_count} open signals >= max {config.MAX_OPEN_SIGNALS}")
        return ScanResult(None, log)

    atr_1h = indicators.atr_last(h1, 14)
    if atr_1h is None:
        log.append("no ATR(1h) — insufficient data")
        return ScanResult(None, log)

    asian_high, asian_low = (asian_range or (None, None))
    detectors = [
        ("london_sweep_reverse", lambda: detect_london_sweep(m15, asian_high, asian_low, atr_1h, regime)),
        ("overlap_vwap_pullback", lambda: detect_vwap_pullback(m15, vwap_now, atr_1h, regime, daily)),
        ("level_break_retest", lambda: detect_break_retest(m15, daily, atr_1h, regime)),
    ]
    for name, fn in detectors:
        cand = fn()
        if cand is None:
            log.append(f"{name}: no pattern")
            continue
        cand.regime_bias = regime.bias
        cand.counter_trend = regime.is_counter_trend(cand.direction)
        ok, why = check_noise_floor(cand.stop_distance, atr_1h)
        if not ok:
            log.append(f"{name}: BLOCKED — {why}")
            continue
        ok, why = check_geometry(cand)
        if not ok:
            log.append(f"{name}: BLOCKED — {why}")
            continue
        cand.tier = "A" if (not cand.counter_trend and cand.rr(cand.tp2) >= 1.8) else "B"
        if cand.counter_trend:
            cand.reasons.append("counter-trend vs daily/H4 EMA stack")
        log.append(f"{name}: PASSED all gates (tier {cand.tier})")
        return ScanResult(cand, log)
    log.append("no setup passed — no signal")
    return ScanResult(None, log)
