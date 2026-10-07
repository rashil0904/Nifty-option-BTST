"""
The 15:20 entry decision, shared by live_entry.py. Same rules as
dry_run_entry.py: VIX filter, Nifty Fut 15:19 close vs 09:15 open,
ATM from spot 15:19 close, OTM offset, 2:1 plan. Read-only market data.
"""

from dataclasses import dataclass
from datetime import date

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


@dataclass(frozen=True)
class NoTrade:
    reason: str


@dataclass(frozen=True)
class EntrySignal:
    direction: str
    option_type: str
    expiry: date
    lot_size: int
    legs: list  # [{role, strike, instrument_token, tradingsymbol, quantity}]


def compute_entry_signal(client, today: date, log=print) -> EntrySignal | NoTrade:
    vix = client.get_india_vix()
    log(f"India VIX: {vix}")
    if should_skip_day(vix):
        return NoTrade(f"VIX {vix} in skip band [17,19]")

    fut = client.get_nifty_fut_instrument(today)
    open_0915 = client.get_nifty_fut_open_0915(today, fut["instrument_token"])
    close_1519 = client.get_nifty_fut_1519_close(today, fut["instrument_token"])
    direction = determine_direction(close_1519, open_0915)
    log(f"Nifty Fut {fut['tradingsymbol']}: 09:15 open {open_0915}, 15:19 close {close_1519} -> {direction.value}")
    if direction is Direction.FLAT:
        return NoTrade("direction FLAT")

    spot_close_1519 = client.get_nifty_spot_1519_close(today)
    expiry = compute_entry_expiry(today, WEEKLY_EXPIRY_WEEKDAY)
    strike_interval, lot_size = client.resolve_nifty_option_grid(expiry)

    atm_strike = calculate_atm_strike(spot_close_1519, strike_interval)
    direction_sign = 1 if direction is Direction.GREEN else -1
    otm_strike = calculate_otm_strike(atm_strike, OTM_OFFSET_POINTS, strike_interval, direction_sign=direction_sign)
    option_type = "CE" if direction is Direction.GREEN else "PE"
    log(f"Spot 15:19 {spot_close_1519}, expiry {expiry}, ATM {atm_strike}, OTM {otm_strike} ({option_type})")

    instruments = {
        "LONG_ATM": client.resolve_option_instrument(atm_strike, option_type, expiry),
        "SHORT_OTM": client.resolve_option_instrument(otm_strike, option_type, expiry),
    }
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
    legs = [
        {
            "role": leg.role.value,
            "strike": leg.strike,
            "instrument_token": instruments[leg.role.value]["instrument_token"],
            "tradingsymbol": instruments[leg.role.value]["tradingsymbol"],
            "quantity": leg.quantity,
        }
        for leg in plan.legs
    ]
    return EntrySignal(direction.value, option_type, expiry, lot_size, legs)
