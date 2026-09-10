# Nifty BTST Ratio Backspread — Strategy Logic (Phase 1)

Standalone project. Nothing here calls a broker or does any I/O — this
is pure, unit-tested strategy logic only, per current scope. Broker
integration, order placement, position tracking, scheduling, and
alerting are **not built yet** (deferred until broker/API is chosen).

## What's implemented

| Module | Purpose |
|---|---|
| `config.py` | Strategy constants (VIX band, OTM offset, expiry weekday, lot ratio, size multiplier). |
| `strategy/vix_filter.py` | `should_skip_day(vix_value)` — True if VIX in [17, 19] inclusive. |
| `strategy/direction.py` | `determine_direction(candle_1514_close, open_0915)` — GREEN / RED / FLAT. |
| `strategy/strikes.py` | `calculate_atm_strike`, `calculate_otm_strike`, `snap_to_strike` — grid rounding, ties round up. |
| `strategy/expiry.py` | `compute_entry_expiry(today, expiry_weekday)` — nearest weekly expiry, rolls to next week if today is expiry day. |
| `strategy/plan.py` | `build_entry_plan(...)` — assembles the 2-long/1-short leg plan (roles, strikes, lots, quantity) from the signals above. |

## Running tests

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -v
```

34/34 tests passing as of last run.

## Explicitly NOT built yet

- Broker integration layer (VIX quote, Future candle fetch, instrument
  master lookup, symbol resolution, order placement/status/cancel).
- Position-tracking JSON file.
- Entry point scripts for 15:15 signal-check-and-entry and 09:18 exit.
- Cron scheduling.
- Logging/alerting beyond nothing (none exists yet).

These are all still open per the original spec and require a broker
decision before any of it can be written, since the calls are
broker-specific.

## Open items requiring explicit sign-off before this touches a broker or real capital

1. **Broker/API is not yet chosen.** No integration code can be written
   until this is picked and its docs confirmed.
2. **Candle-labeling convention** for "15:14 candle close" must be
   verified against a known historical value from whichever data
   source is chosen — this is flagged in `strategy/direction.py` but
   cannot be resolved without live/historical data access.
3. **Strike interval and lot size** must be resolved from the live
   instrument master at runtime (code accepts them as parameters,
   never hardcodes them) — not yet wired to any real source.
4. **Expiry weekday (Tuesday)** is configured in `config.py` per the
   spec's claim that NSE moved Nifty weekly expiry to Tuesday effective
   Sep 2025 — re-verify this is still correct before going live.
5. **Exchange holiday handling for expiry** is not implemented — the
   expiry calculation is calendar-only (nearest Tuesday), with no
   awareness of NSE trading holidays that might shift an expiry date.
   Needs a holiday calendar once the broker/data source is chosen.
6. **Legging risk / combo orders / partial-fill policy** — undecided,
   pending broker choice (need to know if the broker supports
   multi-leg/combo orders before proposing a sequencing and
   partial-fill policy).
7. **Margin requirement** for the 2-long/1-short overnight structure —
   not yet checked, pending broker choice.
8. **Position sizing multiplier** — defaults to `1` in `config.py` as
   specified; do not change without explicit confirmation.
9. **No stop loss** — confirmed: none exists anywhere in this code.
   `strategy/plan.py` and the exit spec (unconditional square-off,
   no P&L check) contain no SL logic, and none should be added
   implicitly.

Nothing in this phase touches a broker, places an order, or is
scheduled to run — by design, per current instructions.
