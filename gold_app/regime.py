"""Macro/trend regime for gold.

v0.1 regime = trend bias from the EMA stack (daily + H4). The spec's real
regime driver — real-yield direction + DXY direction — needs external feeds
that are not wired yet; macro_context() is the clean stub for them and
returns "unknown" rather than faking data.
"""
from dataclasses import dataclass, field

from . import indicators


def macro_context():
    """Stub for the DXY / real-yield feeds (arrive in a later version).

    Returns "unknown" for every input until a real feed is connected.
    """
    return {"dxy": "unknown", "real_yield": "unknown", "us10y": "unknown"}


@dataclass
class RegimeSnapshot:
    bias: str                      # "bullish" | "bearish" | "neutral"
    price: float
    daily_ema20: float = None
    daily_ema50: float = None
    h4_ema50: float = None
    macro: dict = field(default_factory=macro_context)
    notes: list = field(default_factory=list)

    def is_counter_trend(self, direction):
        """A long against a bearish stack (or short against bullish) is
        counter-trend by definition — the card must say so."""
        return (direction == "LONG" and self.bias == "bearish") or \
               (direction == "SHORT" and self.bias == "bullish")


def assess(daily_candles, h4_candles):
    """Trend bias: price vs EMA20/50 on the daily, EMA50 on H4."""
    notes = []
    price = daily_candles[-1]["c"] if daily_candles else 0.0
    d_closes = [c["c"] for c in daily_candles]
    h4_closes = [c["c"] for c in h4_candles]
    e20 = indicators.ema_last(d_closes, 20)
    e50 = indicators.ema_last(d_closes, 50)
    h4e50 = indicators.ema_last(h4_closes, 50)
    h4_price = h4_candles[-1]["c"] if h4_candles else price

    daily_bull = e20 is not None and e50 is not None and price > e20 and price > e50
    daily_bear = e20 is not None and e50 is not None and price < e20 and price < e50
    h4_bull = h4e50 is not None and h4_price > h4e50
    h4_bear = h4e50 is not None and h4_price < h4e50

    if daily_bull and h4_bull:
        bias = "bullish"
    elif daily_bear and h4_bear:
        bias = "bearish"
    else:
        bias = "neutral"
        if daily_bull and h4_bear:
            notes.append("daily stack bullish but H4 below EMA50 — pullback inside uptrend")
        elif daily_bear and h4_bull:
            notes.append("daily stack bearish but H4 above EMA50 — bounce inside downtrend")
        elif not daily_bull and not daily_bear:
            notes.append("price between daily EMA20/EMA50 — no clean daily bias")

    return RegimeSnapshot(bias=bias, price=price, daily_ema20=e20,
                          daily_ema50=e50, h4_ema50=h4e50, notes=notes)
