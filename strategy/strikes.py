"""
ATM/OTM strike calculation. Pure logic, no I/O.

The strike interval itself (e.g. 50 or 100 points) must be resolved by
the caller from the live instrument master at runtime -- it is passed
in here, never hardcoded, since it can differ by index level and by
instrument.
"""

import math


def snap_to_strike(price: float, strike_interval: float) -> float:
    """
    Snap an arbitrary price to the nearest point on the strike grid
    defined by strike_interval. Ties round up (e.g. exactly halfway
    between two strikes rounds to the higher strike), matching common
    trading-system convention rather than Python's banker's rounding.
    """
    if strike_interval <= 0:
        raise ValueError(f"strike_interval must be positive, got {strike_interval}")
    steps = math.floor(price / strike_interval + 0.5)
    return steps * strike_interval


def calculate_atm_strike(underlying_price: float, strike_interval: float) -> float:
    """ATM = underlying price rounded to the nearest valid strike."""
    return snap_to_strike(underlying_price, strike_interval)


def calculate_otm_strike(
    atm_strike: float, offset_points: float, strike_interval: float, *, direction_sign: int
) -> float:
    """
    OTM strike = ATM +/- offset_points, snapped to the nearest valid
    strike on the grid.

    direction_sign: +1 for GREEN (OTM = ATM + offset, CE side),
                     -1 for RED (OTM = ATM - offset, PE side).
    """
    if direction_sign not in (1, -1):
        raise ValueError(f"direction_sign must be 1 or -1, got {direction_sign}")
    raw = atm_strike + (direction_sign * offset_points)
    return snap_to_strike(raw, strike_interval)
