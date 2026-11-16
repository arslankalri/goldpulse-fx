"""Binance USDT-M futures REST client (PAXGUSDT only).

Uses https://www.binance.com as the fapi base: the fapi.binance.com host is
geo-blocked from this VM, the www base works (Malang learned this the hard
way). Stdlib urllib only.
"""
import json
import urllib.parse
import urllib.request

from . import config

_HEADERS = {"User-Agent": "gold-app/0.1"}


def _get(path, params=None):
    url = config.BINANCE_FAPI_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read())


def klines(symbol=config.SYMBOL, interval="1h", limit=100):
    """Return candles as dicts: t (open ms), o/h/l/c/v floats, ct (close ms)."""
    raw = _get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    out = []
    for k in raw:
        out.append({
            "t": int(k[0]),
            "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
            "c": float(k[4]), "v": float(k[5]),
            "ct": int(k[6]),
        })
    return out


def premium_index(symbol=config.SYMBOL):
    """Mark/index/funding snapshot: {mark, index, funding, time}."""
    d = _get("/fapi/v1/premiumIndex", {"symbol": symbol})
    return {
        "mark": float(d["markPrice"]),
        "index": float(d["indexPrice"]),
        "funding": float(d["lastFundingRate"]),
        "time": int(d["time"]),
    }
