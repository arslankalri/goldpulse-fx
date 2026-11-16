"""Text formatting: price rule + signal card (Malang v2.4.1 style).

Price rule (single render path):
  >= 1000   -> thousands separators + exactly 2 decimals  (3,840.99)
  1.. <1000 -> exactly 2 decimals                          (43.35)
  0 < p < 1 -> 4 significant figures                       (0.0249)
  0 / None  -> "0" / "-"
"""
import math

from . import __version__


def fmt_price(p):
    if p is None:
        return "-"
    if p == 0:
        return "0"
    if abs(p) >= 1000:
        return f"{p:,.2f}"
    if abs(p) >= 1:
        return f"{p:.2f}"
    digits = -math.floor(math.log10(abs(p))) + 3
    s = f"{p:.{digits}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def version_label(version=__version__):
    parts = version.split(".")
    if len(parts) >= 3 and parts[2] == "0":
        return "v" + ".".join(parts[:2])
    return "v" + version


def format_signal_card(sig):
    arrow = "🟢 LONG" if sig.direction == "LONG" else "🔴 SHORT"
    lines = [
        f"{arrow}  PAXG/USDT (gold)",
        f"Setup: {sig.setup}  ·  Tier {sig.tier}",
        f"Entry: {fmt_price(sig.entry_low)} – {fmt_price(sig.entry_high)}",
        f"Stop:  {fmt_price(sig.stop)}",
        f"TP1:   {fmt_price(sig.tp1)}  ({sig.rr(sig.tp1):.2f}R)",
        f"TP2:   {fmt_price(sig.tp2)}  ({sig.rr(sig.tp2):.2f}R)",
        f"TP3:   {fmt_price(sig.tp3)}  ({sig.rr(sig.tp3):.2f}R)",
        f"Regime: {sig.regime_bias}" + ("  ⚠️ COUNTER-TREND" if sig.counter_trend else ""),
    ]
    for r in sig.reasons:
        lines.append(f"• {r}")
    lines.append("Decision-support only — not financial advice.")
    lines.append(f"🤖 GOLD APP VERSION:- {version_label()}")
    return "\n".join(lines)


def format_regime(snap):
    lines = [
        f"Regime: {snap.bias}  ·  price {fmt_price(snap.price)}",
        f"Daily EMA20 {fmt_price(snap.daily_ema20)} · EMA50 {fmt_price(snap.daily_ema50)}"
        f" · H4 EMA50 {fmt_price(snap.h4_ema50)}",
        f"Macro (DXY / real yield): {snap.macro.get('dxy')} / {snap.macro.get('real_yield')}"
        "  (feeds not wired yet)",
    ]
    for n in snap.notes:
        lines.append(f"• {n}")
    return "\n".join(lines)
