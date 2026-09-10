from datetime import date

import pytest

from strategy.direction import Direction
from strategy.plan import LegRole, OptionType, build_entry_plan

EXPIRY = date(2026, 9, 15)


def _build(direction, multiplier=1):
    return build_entry_plan(
        direction=direction,
        atm_strike=24650,
        otm_strike=24950 if direction is Direction.GREEN else 24350,
        expiry=EXPIRY,
        lot_size=65,
        long_leg_lots_per_unit=2,
        short_leg_lots_per_unit=1,
        position_size_multiplier=multiplier,
    )


def test_green_direction_builds_ce_legs():
    plan = _build(Direction.GREEN)
    assert all(leg.option_type is OptionType.CE for leg in plan.legs)


def test_red_direction_builds_pe_legs():
    plan = _build(Direction.RED)
    assert all(leg.option_type is OptionType.PE for leg in plan.legs)


def test_flat_direction_raises():
    with pytest.raises(ValueError):
        _build(Direction.FLAT)


def test_default_multiplier_gives_2_long_1_short_lots():
    plan = _build(Direction.GREEN, multiplier=1)
    long_leg = next(leg for leg in plan.legs if leg.role is LegRole.LONG_ATM)
    short_leg = next(leg for leg in plan.legs if leg.role is LegRole.SHORT_OTM)
    assert long_leg.lots == 2
    assert short_leg.lots == 1
    assert long_leg.quantity == 2 * 65
    assert short_leg.quantity == 1 * 65


def test_multiplier_scales_both_legs():
    plan = _build(Direction.GREEN, multiplier=3)
    long_leg = next(leg for leg in plan.legs if leg.role is LegRole.LONG_ATM)
    short_leg = next(leg for leg in plan.legs if leg.role is LegRole.SHORT_OTM)
    assert long_leg.lots == 6
    assert short_leg.lots == 3


def test_legs_carry_correct_strikes_and_expiry():
    plan = _build(Direction.GREEN)
    long_leg = next(leg for leg in plan.legs if leg.role is LegRole.LONG_ATM)
    short_leg = next(leg for leg in plan.legs if leg.role is LegRole.SHORT_OTM)
    assert long_leg.strike == 24650
    assert short_leg.strike == 24950
    assert long_leg.expiry == EXPIRY
    assert short_leg.expiry == EXPIRY


def test_nonpositive_lot_size_raises():
    with pytest.raises(ValueError):
        build_entry_plan(
            direction=Direction.GREEN,
            atm_strike=24650,
            otm_strike=24950,
            expiry=EXPIRY,
            lot_size=0,
            long_leg_lots_per_unit=2,
            short_leg_lots_per_unit=1,
            position_size_multiplier=1,
        )


def test_nonpositive_multiplier_raises():
    with pytest.raises(ValueError):
        _build(Direction.GREEN, multiplier=0)
