# Gold (PAXG) Signal App — Research & Design
Written 2026-11-16. Purpose: a SEPARATE app from Malang, gold-only, decision-support (never places orders), built to the same evidence standard as the Futures Signals Lab and Malang v2.4: quality over quantity, honest TP-before-SL accounting, 30+ resolved signals before anyone calls it proven.

## 1. What PAXG actually is
- PAXG (Pax Gold, Paxos) = 1 token backed by 1 fine troy ounce of an LBMA Good Delivery gold bar in London vaults. It tracks spot gold (XAU/USD) 1:1.
- On Binance he trades **PAXGUSDT perpetual futures** (USDT-margined) — the liquid venue: ~$65M/24h perp volume on Binance (largest share of ~$190M global PAXG perp volume), ~$92M open interest on Binance. Spot PAXGUSDT is much thinner (~$11M/24h) — use the perp for signals and trading.
- Perp mark vs index: at research time mark $3,840.94 vs index $3,842.07 — the perp tracks spot gold tightly (small premium/discount, usually <0.1%).
- Funding on PAXG perps is normally tiny (today +0.0036%) — crowding rarely screams the way it does on alts. Funding stays a check, not a headline veto.
- **PAXG-specific quirk #1 — weekends:** traditional gold (COMEX/spot) closes Friday evening to Sunday evening US time; PAXG trades 24/7. Weekend PAXG moves are crypto-flow noise with no gold-market anchor and often snap back at the Sunday/Monday reopen. Rule: no new signals Sat–Sun, or mark them low-tier by default.
- **PAXG-specific quirk #2 — liquidity hours:** PAXG volume follows the gold sessions. Off-hours (Asian morning) spreads widen and moves are unreliable — same lesson as forex gold.

## 2. What actually moves gold (the driver stack, in order)
1. **Real interest rates (10y TIPS yield)** — historically THE driver (long-run correlation ≈ −0.8). Gold pays no yield; when real yields fall, gold's opportunity cost falls and gold rises. Weakened since 2022 (see #3) but still the baseline gravity.
2. **The US dollar (DXY)** — gold is priced in dollars; inverse correlation ≈ −0.6. Strong dollar day = headwind for gold, mechanically.
3. **Central-bank buying** — 1,000+ tonnes/yr in 2022–2024, 863t in 2025 (World Gold Council). Price-insensitive, long-term buying = the structural floor under this bull market, and the reason the real-yield model "broke".
4. **Fed expectations & US data** — the day-to-day trigger: CPI, NFP, PCE, FOMC, GDP, retail sales, JOLTS, Powell speeches. Gold can move $30–80 in minutes on a CPI surprise. This is gold's event calendar (see §4).
5. **Safe-haven / geopolitics** — wars, banking stress, sanctions → fast bids; these spikes often partially retrace, unlike rate-driven trends.
6. **Positioning & flows** — COMEX COT (managed money), gold ETF flows, options at round numbers. Useful as crowding context, not a trigger.

**Practical translation for the app:** gold's "BTC regime" equivalent is a **macro regime filter = real-yield direction + DXY direction**. A gold long fighting both rising real yields AND a rising dollar is counter-trend by definition — the app must say so on the card, the way Malang flags counter_trend.

## 3. Sessions — gold is a session market (all times JST, winter)
Unlike 24/7 crypto, gold's real moves happen in windows:
- **Asian session (09:00–17:00 JST):** thin, ranging. Gold often just builds the "Asian range" that London later sweeps. No signals except range extremes marked for later.
- **London open (17:00 JST):** first real liquidity. Classic play: sweep of the Asian range high/low, then the day's direction.
- **LBMA auctions:** 10:30 & 15:00 London (19:30 & 00:00 JST) — benchmark fixings, brief volatility.
- **US data (usually 22:30 JST):** CPI/NFP/etc. — the biggest scheduled spikes.
- **London–New York overlap (≈22:00–01:00 JST):** deepest liquidity, cleanest trends, COMEX open inside it. **This is gold's prime signal window.**
- **Late NY / rollover (≈06:00 JST):** spreads widen, avoid.

For a trader in Japan this is actually convenient: gold's day is his evening/night, not his school hours.

## 4. Event calendar (gold-specific)
No new signals 30 min before → 30 min after: **CPI, NFP, FOMC decision + Powell presser, PCE, GDP, retail sales**. Watch also: Fed chair speeches, US Treasury auctions on stressed days, and unscheduled geopolitics (headline risk — the AI/news sensor idea from the Malang v2.5 discussion applies here too, later). Malang's server calendar already carries CPI 2026-12-10 and FOMC 2026-12-09 — the gold app needs the full US calendar, seeded the same way.

## 5. Indicator stack (levels lead, indicators confirm)
- **Levels first:** prior day high/low, prior week high/low, round numbers ($50/$100 handles — gold respects them), swing S/R, Fibonacci retracement (gold's trending swings honour the 0.618 "golden pocket" unusually well).
- **ATR(14)** — the risk ruler. Live check 2026-11-16: daily ATR ≈ **$85/day (~2.2% of price)**. Gold moves 2–4× more per day than in 2024; fixed-dollar stops are suicide. Port Malang's rule directly: **stop ≥ 1.2 × ATR(1h), target geometry ≥1.5R to TP2**, position size from fixed 1% risk.
- **Trend stack:** EMA 20/50 (daily + H4) for bias; price vs EMA50 H4 = the trade-direction filter (longs only above, shorts only below, unless a labelled counter-trend setup passes every other check).
- **Session VWAP** — intraday fair value. On Binance PAXG the volume is real exchange volume (unlike forex tick volume), so VWAP is genuinely meaningful here. Pullbacks to VWAP in the overlap are a core setup.
- **RSI(14)** — filter and divergence only, never a standalone signal (gold trends too hard for raw overbought/oversold fading — the Hafeez lesson, in a different market).
- **MACD (H4)** — momentum confirmation, optional.
- **Context feeds (regime, not triggers):** DXY, US 10y yield / 10y TIPS real yield, BTC (risk sentiment), silver + gold/silver ratio. Displayed on the morning brief, checked in the regime filter.

## 6. Live snapshot — 2026-11-16 ~16:11 JST (Binance, verified)
- PAXGUSDT perp: **$3,840.99**, +0.60%/24h, range $3,812–$3,886, funding +0.0036% (neutral).
- Daily trend: price **below EMA20 ($3,970) and EMA50 ($4,065)**, RSI14 42.2 → short-term corrective downtrend inside the larger bull market; 60-day range $3,760–$4,394 — price is near the bottom of its 60-day range, ~$80 above the $3,760 floor.
- Read: no signal issued by this research — but the app, if live today, would be in "shorts/pullback mode with a hard floor at $3,760; a daily close below $3,760 opens the next leg; longs are counter-trend until EMA20 is reclaimed."

## 7. App design (v0.1) — separate from Malang, same discipline
- **Instrument:** PAXGUSDT perp only. Context: DXY, US10Y, real yield (FRED/public feeds), BTC.
- **Cadence:** scans every 15 min, but signal-eligible only in London + overlap windows (17:00–01:30 JST); Asian session = observe/record only; weekends = no new signals.
- **Setups v0.1 (three, deliberately few):**
  1. *London sweep & reverse* — London takes out the Asian range extreme, closes back inside, enter on the retest against the sweep.
  2. *Overlap VWAP pullback* — H4 trend-aligned pullback to session VWAP during the overlap, rejection candle, enter on retest.
  3. *Level break & retest* — daily/H4 S/R break during London/NY, retest holds, continuation entry (Malang's breakout_held, gold edition).
- **Hard gates (ported from Malang v2.4):** ATR noise floor; TP1 ≥0.8R and TP2 ≥1.5R at worst fill or no signal; event shield (§4); macro regime stated on every card (real-yield/DXY direction; counter-trend labelled); fill-or-expire (6h); bank TP1 → stop to entry; max 2 open signals (gold is one instrument — concentration is inherent).
- **Journal & scoreboard:** identical accounting to Malang — TP-before-SL sequencing, era split by version, reviews with why-tags, /score equivalent. Gold app must earn trust the same way: **30+ resolved shadow signals before any live reliance.**
- **Delivery:** TO BE DECIDED by Arslan — (a) Telegram bot like Malang, (b) web dashboard app (GitHub-hosted code + a page he opens), (c) both. The engine core is identical either way; only the output layer differs.
- **Hosting:** his Oracle bot-server, next to Malang (proven deploy path), code in its own GitHub repo.

## 8. What NOT to do
- No forex-broker XAUUSD feed mixing: signals are computed on Binance PAXG (his trading venue) — levels from another venue's gold feed would be off by the spread/premium.
- No scalping the Asian session, no fixed-dollar stops, no signals into CPI/NFP/FOMC, no weekend signals, no Martingale/DCA-into-losers (the Hafeez package stays rejected in every market).
- Not financial advice; decision-support only, same as Malang. He places every trade himself.
