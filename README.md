# Gold App — PAXG Signal Engine + Dashboard

A **separate, gold-only** sibling of Malang: a decision-support signal app for
**PAXGUSDT perpetual futures on Binance** (PAXG = tokenised gold, 1 token =
1 fine troy ounce). Design rationale lives in `RESEARCH_AND_DESIGN.md`.

**Decision-support only.** This app never places orders, never touches an
account, and its output is not financial advice. Arslan places every trade
himself. Like Malang, the app must earn trust: **30+ resolved shadow signals
with honest TP-before-SL accounting before any live reliance.**

## Layout

```
gold_app/     engine core (Python, stdlib only)
  config.py     thresholds as named constants (GOLDAPP_* env overrides)
  data.py       Binance futures REST via https://www.binance.com
                (fapi.binance.com is geo-blocked from the VM; www works)
  indicators.py EMA, ATR(14), RSI(14), session VWAP, swings, prior-day levels
  regime.py     daily + H4 EMA-stack bias; DXY/real-yield feeds are a stub
                returning "unknown" (never faked)
  engine.py     the 3 setups + all hard gates
  journal.py    append-only merge-save journal + honest tracker
  format.py     price formatting + signal card text
  main.py       dry-run entry (one live scan + writes dashboard/state.json)
  service.py    production runner: 15-min scan/track loop + dashboard HTTP
                server (stdlib, port GOLDAPP_PORT=8791) + /healthz
dashboard/    static web dashboard (no build step, no frameworks, no CDN)
  index.html    live panel (client-side Binance fetch) + signal/scoreboard
                panels rendered from state.json
  state.json    written by the engine (sample committed from a real dry-run)
events.json   event-shield calendar (UTC)
tests/        unit tests (stdlib unittest)
```

## Run the dry-run

```bash
cd ~/workspace/gold-signals-app
python3 -m gold_app.main     # one live scan; prints regime + verdict;
                             # rewrites dashboard/state.json
python3 -m unittest discover -s tests -t .   # run the test suite
```

To view the dashboard locally: `python3 -m http.server --directory dashboard`
then open `http://localhost:8000/`. (Hosting is decided later — see below.)

## v0.1 rules (ported from Malang v2.4)

- **Instrument:** PAXGUSDT perp only. Levels are computed on Binance PAXG —
  never mixed with a forex XAUUSD feed.
- **Sessions (JST):** signals only in the London + London/NY overlap window
  **17:00–01:30**. The post-midnight segment counts as the previous day's
  session. **Weekends blocked** — PAXG drifts unanchored while COMEX is
  closed. Asian session = observe only (it builds the range London sweeps).
- **Setups (three, deliberately few):**
  1. `london_sweep_reverse` — London sweeps the Asian range extreme, closes
     back inside; targets: range mid → opposite edge → extension.
  2. `overlap_vwap_pullback` — H4/daily trend-aligned pullback to session
     VWAP (anchored 17:00 JST) with a rejection candle.
  3. `level_break_retest` — prior-day high/low breaks, retest holds,
     continuation (R-multiple targets in this scaffold).
- **Hard gates — a signal must pass EVERY one or it does not exist:**
  - stop distance ≥ **1.2 × ATR(1h)** (noise floor; a structural stop inside
    the floor is widened to the floor and the widening is noted on the card)
  - **TP1 ≥ 0.8R and TP2 ≥ 1.5R at worst fill** (worst edge of the entry zone)
  - **event shield:** no signals 30 min before → 30 min after events in
    `events.json` (seeded: FOMC 2026-12-09 19:00–20:00Z, CPI 2026-12-10 13:30Z)
  - **max 2 open signals**; **fill-or-expire 6h**
  - regime stated on every card; counter-trend (vs the EMA stack) is flagged
    and can never be Tier A
- **Management/accounting (journal):** fills graded at worst fill; TP/SL
  resolved candle-by-candle with the **stop counted first** when one candle
  touches both; **bank TP1 → stop moves to entry**; losers are never
  deleted; records are stamped with the app version (era split).

## state.json schema (dashboard contract)

Written by the engine on every scan (the dry-run writes it too):

| key | content |
|---|---|
| `app`, `version`, `symbol`, `generated_at` | identity + scan time (UTC ISO) |
| `market` | `{mark, index, funding}` from Binance premiumIndex |
| `regime` | `{bias, price, daily_ema20, daily_ema50, h4_ema50, macro, notes}` — macro values are `"unknown"` until feeds are wired |
| `latest_scan` | `{at, signal, log}` — `signal` is a journal-shaped record plus a rendered `card`, or `null`; `log` lists every gate/detector verdict, so "no signal" always says why |
| `open_signals` | journal records with status `PENDING`/`OPEN` (incl. `tp_hits`, `current_stop`) |
| `scoreboard` | `{era, issued, filled, pending, open, tp1, tp2, tp3, sl, breakeven, expired, timeouts, resolved, wins, losses}` — win = closed after reaching TP1 |

The dashboard's **live panel does not use state.json** — it fetches Binance
public endpoints directly in the browser and recomputes EMA/RSI/ATR/regime
client-side, so price and regime stay live between engine scans.

## Delivery & hosting — decided: web dashboard on the Oracle server

The user chose a **web dashboard** over Telegram (2026-11-16), hosted on his
Oracle bot-server next to Malang, with this repo as the code home.

**Production runner** (`gold_app/service.py`, started by `run.sh` under the
`gold-app` systemd unit): every 15 minutes it fetches PAXG data, tracks open
journal records, runs one scan (journaling any signal that passes every
gate), and rewrites `dashboard/state.json`; the same process serves
`dashboard/` read-only over HTTP on port **8791** and answers `/healthz`
with the version + last scan time. The journal lives in
`GOLDAPP_DATA_DIR` (`/opt/gold-app/data` under systemd). Decision-support
only — the service holds no keys and places no orders.

**Server install (one time):** paste `deploy/INSTALL_CLOUD_SHELL.sh` into a
Cloud Shell SSH session on the server. It creates `/opt/gold-app`, installs
the systemd unit, the `/usr/local/bin/gold-app-deploy` helper + its sudoers
rule (ocarun may run only that helper), and the deploy staging dir.

**Deploys** mirror Malang: build with `deploy/build_tarball.sh`
(`gold-app-v<version>-deploy.tar.gz`), stage it at
`/var/tmp/gold-app-deploy/incoming.tar.gz` via the OCI API, then the helper
stops the service, backs up the code, swaps code paths only (the live
`state.json` and `data/` survive), runs the test suite (restoring the
backup on failure), and restarts.

## Not in v0.1 (by design)

No Telegram, no order placement, no DXY/yield feeds (regime stub returns
"unknown"), no news/AI sensor layer (that's a v2.5-era idea, after data
exists — same sequence as Malang).
