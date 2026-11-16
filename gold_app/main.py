"""Dry-run entry: one live scan against Binance PAXG data.

Fetches live candles, prints the regime snapshot + any signal card (or
"no signal" with the gate log), and writes dashboard/state.json so the web
dashboard renders real content end-to-end.

Decision-support only: no Telegram, no server loop, no orders, and the
dry-run does NOT write to the journal.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gold_app import __version__, config, data, engine, format as fmt, indicators, regime
from gold_app.journal import Journal, scoreboard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = engine.JST


def asian_range_today(m15, now_jst):
    """(high, low) of today's Asian session 09:00-17:00 JST, or (None, None)."""
    todays = []
    for c in m15:
        t = datetime.fromtimestamp(c["t"] / 1000, JST)
        if t.date() == now_jst.date() and config.ASIAN_START_HOUR_JST <= t.hour < config.ASIAN_END_HOUR_JST:
            todays.append(c)
    if not todays:
        return None, None
    return max(c["h"] for c in todays), min(c["l"] for c in todays)


def session_vwap_now(m15, now_jst):
    """VWAP anchored at the most recent 17:00 JST (London open)."""
    anchor = now_jst.replace(hour=config.SESSION_START_HOUR_JST,
                             minute=config.SESSION_START_MIN_JST, second=0, microsecond=0)
    if now_jst < anchor:
        anchor -= timedelta(days=1)
    anchor_ms = int(anchor.timestamp() * 1000)
    since = [c for c in m15 if c["t"] >= anchor_ms]
    if not since:
        return None
    return indicators.session_vwap(since)[-1]


def build_state(now_utc, prem, snap, result, journal_records):
    pd = None
    open_signals = [r for r in journal_records if r["status"] in ("PENDING", "OPEN")]
    state = {
        "app": "gold-app",
        "version": __version__,
        "symbol": config.SYMBOL,
        "generated_at": now_utc.isoformat(),
        "market": {"mark": prem["mark"], "index": prem["index"], "funding": prem["funding"]},
        "regime": {
            "bias": snap.bias, "price": snap.price,
            "daily_ema20": snap.daily_ema20, "daily_ema50": snap.daily_ema50,
            "h4_ema50": snap.h4_ema50, "macro": snap.macro, "notes": snap.notes,
        },
        "latest_scan": {
            "at": now_utc.isoformat(),
            "signal": None,
            "log": result.log,
        },
        "open_signals": open_signals,
        "scoreboard": scoreboard(journal_records),
    }
    if result.signal is not None:
        rec = result.signal.to_record(int(now_utc.timestamp() * 1000))
        rec["card"] = fmt.format_signal_card(result.signal)
        state["latest_scan"]["signal"] = rec
    return state


def main():
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc.astimezone(JST)
    prem = data.premium_index()
    daily = data.klines(interval="1d", limit=120)
    h4 = data.klines(interval="4h", limit=120)
    h1 = data.klines(interval="1h", limit=120)
    m15 = data.klines(interval="15m", limit=300)

    snap = regime.assess(daily, h4)
    asian = asian_range_today(m15, now_jst)
    vwap = session_vwap_now(m15, now_jst)
    events = engine.load_events(os.path.join(ROOT, "events.json"))

    journal_path = os.path.join(ROOT, "data", "journal.json")
    journal_records = Journal(journal_path).load() if os.path.exists(journal_path) else []
    open_count = sum(1 for r in journal_records if r["status"] in ("PENDING", "OPEN"))

    result = engine.scan(now_utc, m15, h1, daily, snap, asian, vwap, events,
                         open_count=open_count)

    print(f"=== GOLD APP {fmt.version_label()} dry-run — {now_jst:%Y-%m-%d %H:%M} JST ===")
    print(f"PAXGUSDT mark {fmt.fmt_price(prem['mark'])} · index {fmt.fmt_price(prem['index'])}"
          f" · funding {prem['funding'] * 100:.4f}%")
    print(fmt.format_regime(snap))
    atr1h = indicators.atr_last(h1, 14)
    print(f"ATR(1h) {fmt.fmt_price(atr1h)} · Asian range "
          f"{fmt.fmt_price(asian[0])} / {fmt.fmt_price(asian[1])} · session VWAP {fmt.fmt_price(vwap)}")
    print("--- scan ---")
    for line in result.log:
        print(f"  {line}")
    if result.signal is not None:
        print(fmt.format_signal_card(result.signal))
    else:
        print("NO SIGNAL")

    state = build_state(now_utc, prem, snap, result, journal_records)
    state_path = os.path.join(ROOT, "dashboard", "state.json")
    with open(state_path, "w") as f:
        json.dump(state, f, indent=1)
    print(f"(wrote {state_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
