"""
Read-only dry run of the 15:15 entry signal, using real Kite data.

DOES NOT PLACE, MODIFY, OR CANCEL ANY ORDER. It fetches real market
data and runs it through the pure strategy functions in strategy/, then
prints what the strategy *would* do. Nothing here touches a broker
order endpoint.

Run at/after 15:15 IST (before that, today's 15:14 candle won't exist
yet and this will raise CandleNotFoundError -- that's intentional,
not a bug to work around).

    .venv/bin/python scripts/dry_run_entry.py
"""

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from broker.kite_client import KiteDataClient
from config import (
    LONG_LEG_LOTS_PER_UNIT,
    OTM_OFFSET_POINTS,
    POSITION_SIZE_MULTIPLIER,
    SHORT_LEG_LOTS_PER_UNIT,
    WEEKLY_EXPIRY_WEEKDAY,
)
from strategy.direction import Direction, determine_direction
from strategy.expiry import compute_entry_expiry
from strategy.plan import build_entry_plan
from strategy.strikes import calculate_atm_strike, calculate_otm_strike
from strategy.vix_filter import should_skip_day

IST = ZoneInfo("Asia/Kolkata")


def main() -> None:
    now_ist = datetime.now(IST)
    today = now_ist.date()
    print(f"=== DRY RUN (no orders placed) --- {now_ist.isoformat()} ===\n")

    client = KiteDataClient.from_env()

    vix = client.get_india_vix()
    print(f"India VIX: {vix}")
    if should_skip_day(vix):
        print(f"VIX {vix} is within [17, 19] -> SKIP DAY, no trade.")
        return
    print("VIX outside skip band -> proceeding.\n")

    fut = client.get_nifty_fut_instrument(today)
    print(f"Nifty Fut contract: {fut['tradingsymbol']} (token {fut['instrument_token']}, expiry {fut['expiry']})")

    open_0915 = client.get_nifty_fut_open_0915(today, fut["instrument_token"])
    close_1514 = client.get_nifty_fut_1514_close(today, fut["instrument_token"])
    print(f"09:15 open: {open_0915}")
    print(f"15:14 close: {close_1514}")

    direction = determine_direction(close_1514, open_0915)
    print(f"Direction: {direction.value}\n")

    if direction is Direction.FLAT:
        print("FLAT -> no trade today.")
        return

    spot_close_1514 = client.get_nifty_spot_1514_close(today)
    print(f"Nifty Spot 15:14 close (used for ATM strike): {spot_close_1514}")

    expiry = compute_entry_expiry(today, WEEKLY_EXPIRY_WEEKDAY)
    print(f"Expiry: {expiry}")

    strike_interval, lot_size = client.resolve_nifty_option_grid(expiry)
    print(f"Strike interval: {strike_interval}, lot size: {lot_size}")

    atm_strike = calculate_atm_strike(spot_close_1514, strike_interval)
    direction_sign = 1 if direction is Direction.GREEN else -1
    otm_strike = calculate_otm_strike(
        atm_strike, OTM_OFFSET_POINTS, strike_interval, direction_sign=direction_sign
    )
    print(f"ATM strike: {atm_strike}, OTM strike: {otm_strike}\n")

    option_type = "CE" if direction is Direction.GREEN else "PE"
    atm_instrument = client.resolve_option_instrument(atm_strike, option_type, expiry)
    otm_instrument = client.resolve_option_instrument(otm_strike, option_type, expiry)
    print(f"ATM instrument: {atm_instrument['tradingsymbol']}")
    print(f"OTM instrument: {otm_instrument['tradingsymbol']}\n")

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

    print("=== Entry plan (NOT executed) ===")
    for leg in plan.legs:
        print(
            f"  {leg.role.value}: {option_type} {leg.strike} exp {leg.expiry} "
            f"-- {leg.lots} lot(s) x {leg.lot_size} = {leg.quantity} qty"
        )
    print("\nNo order was placed. This was a read-only dry run.")


if __name__ == "__main__":
    main()
