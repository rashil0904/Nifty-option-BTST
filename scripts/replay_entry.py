"""
Replay the entry-signal logic against a past date's real data.

DOES NOT PLACE, MODIFY, OR CANCEL ANY ORDER -- pure historical
read + the same pure strategy functions used everywhere else.

Usage:
    .venv/bin/python scripts/replay_entry.py 2026-09-09

Notes:
  - VIX is approximated from the 15:14 candle close (see
    get_historical_vix_at_1515) since a historical "instantaneous"
    15:15 quote isn't retrievable after the fact -- this is a
    replay approximation, not what the live 15:15 script does today
    (which reads a live quote).
  - Expiry/strike/lot-size resolution uses the CURRENT instrument
    master, not a historical snapshot -- Kite doesn't expose old
    instrument master dumps, so strike interval/lot size for a past
    date assumes they haven't changed since. Flag to the user if
    that's not a safe assumption for the date in question.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker.kite_client import CandleNotFoundError, InstrumentNotFoundError, KiteDataClient
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


def replay(target_date: date) -> None:
    print(f"=== REPLAY for {target_date} (read-only, no orders) ===\n")
    client = KiteDataClient.from_env()

    vix = client.get_historical_vix_at_1515(target_date)
    print(f"VIX (approx, from 15:14 candle close): {vix}")
    if should_skip_day(vix):
        print(f"VIX {vix} in [17, 19] -> would have SKIPPED the day, no trade.")
        return
    print("VIX outside skip band -> would have proceeded.\n")

    fut = client.get_nifty_fut_instrument(target_date)
    print(f"Nifty Fut contract used: {fut['tradingsymbol']} (token {fut['instrument_token']})")

    open_0915 = client.get_nifty_fut_open_0915(target_date, fut["instrument_token"])
    close_1514 = client.get_nifty_fut_1514_close(target_date, fut["instrument_token"])
    print(f"09:15 open: {open_0915}")
    print(f"15:14 close: {close_1514}")

    direction = determine_direction(close_1514, open_0915)
    print(f"Direction: {direction.value}\n")

    if direction is Direction.FLAT:
        print("FLAT -> no trade would have been taken.")
        return

    spot_close_1514 = client.get_nifty_spot_1514_close(target_date)
    print(f"Nifty Spot 15:14 close (used for ATM strike): {spot_close_1514}")

    expiry = compute_entry_expiry(target_date, WEEKLY_EXPIRY_WEEKDAY)
    print(f"Expiry that would have been used: {expiry}")

    strike_interval, lot_size = client.resolve_nifty_option_grid(expiry)
    print(f"Strike interval (current instrument master): {strike_interval}, lot size: {lot_size}")

    atm_strike = calculate_atm_strike(spot_close_1514, strike_interval)
    direction_sign = 1 if direction is Direction.GREEN else -1
    otm_strike = calculate_otm_strike(
        atm_strike, OTM_OFFSET_POINTS, strike_interval, direction_sign=direction_sign
    )
    print(f"ATM strike: {atm_strike}, OTM strike: {otm_strike}\n")

    option_type = "CE" if direction is Direction.GREEN else "PE"
    try:
        atm_instrument = client.resolve_option_instrument(atm_strike, option_type, expiry)
        otm_instrument = client.resolve_option_instrument(otm_strike, option_type, expiry)
        print(f"ATM instrument: {atm_instrument['tradingsymbol']}")
        print(f"OTM instrument: {otm_instrument['tradingsymbol']}\n")
    except InstrumentNotFoundError as exc:
        print(f"(Could not resolve current-day symbols for these strikes: {exc})\n")

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

    print("=== Entry plan that would have been taken ===")
    for leg in plan.legs:
        print(
            f"  {leg.role.value}: {option_type} {leg.strike} exp {leg.expiry} "
            f"-- {leg.lots} lot(s) x {leg.lot_size} = {leg.quantity} qty"
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: replay_entry.py YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)
    try:
        target = date.fromisoformat(sys.argv[1])
    except ValueError:
        print(f"Invalid date: {sys.argv[1]!r}, expected YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    try:
        replay(target)
    except CandleNotFoundError as exc:
        print(f"Missing candle data for {target}: {exc}", file=sys.stderr)
        sys.exit(1)
