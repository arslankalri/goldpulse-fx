"""Pure indicator functions over candle dicts ({t,o,h,l,c,v}).

No external deps. Series functions return lists aligned with the input,
with None during warm-up.
"""


def ema(values, period):
    """Exponential moving average (SMA-seeded)."""
    if period <= 0 or not values:
        return []
    out = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def ema_last(values, period):
    s = ema(values, period)
    return s[-1] if s else None


def true_ranges(candles):
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c["h"] - c["l"])
        else:
            pc = candles[i - 1]["c"]
            trs.append(max(c["h"] - c["l"], abs(c["h"] - pc), abs(c["l"] - pc)))
    return trs


def atr(candles, period=14):
    """Wilder ATR. Returns aligned list, None before index period-1."""
    n = len(candles)
    out = [None] * n
    if n < period:
        return out
    trs = true_ranges(candles)
    first = sum(trs[:period]) / period
    out[period - 1] = first
    prev = first
    for i in range(period, n):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def atr_last(candles, period=14):
    s = atr(candles, period)
    return s[-1] if s else None


def rsi(closes, period=14):
    """Wilder RSI(14). Returns aligned list, None during warm-up."""
    n = len(closes)
    out = [None] * n
    if n <= period:
        return out
    gains, losses = [], []
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    out[period] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    for i in range(period, n - 1):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        out[i + 1] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return out


def session_vwap(candles):
    """Cumulative VWAP from the first candle given (the session anchor).

    Caller slices candles from the session start. Uses typical price and
    real exchange volume (meaningful on Binance, unlike forex tick volume).
    Returns an aligned list; None while cumulative volume is zero.
    """
    out = []
    cum_pv = 0.0
    cum_v = 0.0
    for c in candles:
        tp = (c["h"] + c["l"] + c["c"]) / 3.0
        cum_pv += tp * c["v"]
        cum_v += c["v"]
        out.append(cum_pv / cum_v if cum_v > 0 else None)
    return out


def swing_highs(candles, left=2, right=2):
    """[(index, price)] where high is the strict max of its window."""
    out = []
    for i in range(left, len(candles) - right):
        h = candles[i]["h"]
        if all(candles[j]["h"] < h for j in range(i - left, i + right + 1) if j != i):
            out.append((i, h))
    return out


def swing_lows(candles, left=2, right=2):
    out = []
    for i in range(left, len(candles) - right):
        lo = candles[i]["l"]
        if all(candles[j]["l"] > lo for j in range(i - left, i + right + 1) if j != i):
            out.append((i, lo))
    return out


def prior_day_high_low(daily_candles):
    """(high, low) of the previous completed day.

    Assumes the last candle is the current (incomplete) day, so the prior
    day is candles[-2]. Returns None if there aren't enough candles.
    """
    if len(daily_candles) < 2:
        return None
    prev = daily_candles[-2]
    return (prev["h"], prev["l"])
