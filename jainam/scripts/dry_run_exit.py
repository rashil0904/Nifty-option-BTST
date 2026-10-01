"""
Read-only dry run of the 09:18 unconditional exit, using real Jainam
(XTS) data -- Market Data API only, no Interactive API required.

This project never places real orders, so there is no real broker
position to query in the first place -- instead this REPLAYS the
previous trading day's entry signal (same logic as dry_run_entry.py)
to figure out what position would exist, then fetches the CURRENT live
price for those same legs. That's why this doesn't need Interactive
API: it never queries account state, only market data for instruments
it already knows how to resolve.

DOES NOT PLACE, MODIFY, OR CANCEL ANY ORDER. There is deliberately NO
P&L check and NO stop loss -- per spec, the real exit is unconditional
square-off, no conditions.

Run at/after 09:18 IST for the "price at square-off" number to be
meaningful; it'll still run at other times, just quoting whatever the
current live price is instead.

    .venv/bin/python jainam/scripts/dry_run_exit.py
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import (
    LONG_LEG_LOTS_PER_UNIT,
    OTM_OFFSET_POINTS,
    POSITION_SIZE_MULTIPLIER,
    SHORT_LEG_LOTS_PER_UNIT,
    WEEKLY_EXPIRY_WEEKDAY,
)
from jainam.broker.xts_client import XTSDataClient
from strategy.direction import Direction, determine_direction
from strategy.expiry import compute_entry_expiry
from strategy.plan import build_entry_plan
from strategy.strikes import calculate_atm_strike, calculate_otm_strike
from strategy.vix_filter import should_skip_day

IST = ZoneInfo("Asia/Kolkata")


def _previous_trading_day(d: date) -> date:
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # Sat/Sun, calendar-only -- no NSE holiday calendar
        prev -= timedelta(days=1)
    return prev


def main() -> None:
    now_ist = datetime.now(IST)
    today = now_ist.date()
    entry_date = _previous_trading_day(today)
    print(f"=== DRY RUN EXIT -- Jainam/XTS (no orders placed) --- {now_ist.isoformat()} ===\n")
    print(f"Replaying the entry signal for the previous trading day ({entry_date}) to know what")
    print("position would exist -- no real position is ever tracked, same as the entry script.\n")

    client = XTSDataClient.from_env()

    vix = client.get_historical_vix_at_1515(entry_date)
    print(f"{entry_date} VIX (approx, from 15:14 candle close): {vix}")
    if should_skip_day(vix):
        print(f"VIX {vix} was in skip band -> no trade would have been entered -> nothing to exit.")
        return

    fut = client.get_nifty_fut_instrument(entry_date)
    open_0915 = client.get_nifty_fut_open_0915(entry_date, fut["instrument_token"])
    close_1514 = client.get_nifty_fut_1514_close(entry_date, fut["instrument_token"])
    direction = determine_direction(close_1514, open_0915)
    print(f"{entry_date} direction: {direction.value}")

    if direction is Direction.FLAT:
        print("FLAT -> no trade would have been entered -> nothing to exit.")
        return

    spot_close_1514 = client.get_nifty_spot_1514_close(entry_date)
    expiry = compute_entry_expiry(entry_date, WEEKLY_EXPIRY_WEEKDAY)
    strike_interval, lot_size = client.resolve_nifty_option_grid(expiry)

    atm_strike = calculate_atm_strike(spot_close_1514, strike_interval)
    direction_sign = 1 if direction is Direction.GREEN else -1
    otm_strike = calculate_otm_strike(atm_strike, OTM_OFFSET_POINTS, strike_interval, direction_sign=direction_sign)
    option_type = "CE" if direction is Direction.GREEN else "PE"

    plan = build_entry_plan(
        direction=direction,
        atm_strike=atm_strike,
        otm_strike=otm_strike,
        expiry=expiry,
        lot_size=lot_size,
        long_leg_lots_per_unit=LONG_LEG_LOTS_PER_UNIT,
        short_leg_lots_per_unit=SHORT_LEG_LOTS_PER_UNIT,
        position_size_multiplier=POSITION_SIZE_MULTIPLIER,
    )

    print(f"\nPosition that would be open (from {entry_date}'s signal):")
    for leg in plan.legs:
        print(f"  {leg.role.value}: {option_type} {leg.strike} exp {leg.expiry} -- qty {leg.quantity}")

    print("\n=== Would square off now (unconditional, no P&L check) ===")
    for leg in plan.legs:
        instrument = client.resolve_option_instrument(leg.strike, option_type, expiry)
        current_price = client.get_option_ltp(instrument["instrument_token"])
        side = "SELL" if leg.role.value == "LONG_ATM" else "BUY"
        print(
            f"  {instrument['tradingsymbol']}: qty {leg.quantity} -> {side} {leg.quantity} to close "
            f"@ current LTP {current_price}"
        )

    print("\nNo order was placed. This was a read-only dry run.")


if __name__ == "__main__":
    main()
