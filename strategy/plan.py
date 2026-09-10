"""
Assembles the 2:1 ratio backspread entry plan from already-computed
signals (direction, strikes, expiry, lot size). Pure logic, no I/O --
no broker calls, no order placement. This describes *what* to trade;
placing the orders is a broker-layer concern (not built yet).
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum

from strategy.direction import Direction


class OptionType(Enum):
    CE = "CE"
    PE = "PE"


class LegRole(Enum):
    LONG_ATM = "LONG_ATM"
    SHORT_OTM = "SHORT_OTM"


@dataclass(frozen=True)
class Leg:
    role: LegRole
    option_type: OptionType
    strike: float
    expiry: date
    lots: int
    lot_size: int
    quantity: int  # lots * lot_size, the actual order quantity


@dataclass(frozen=True)
class EntryPlan:
    direction: Direction
    atm_strike: float
    otm_strike: float
    expiry: date
    legs: tuple[Leg, ...]


def build_entry_plan(
    *,
    direction: Direction,
    atm_strike: float,
    otm_strike: float,
    expiry: date,
    lot_size: int,
    long_leg_lots_per_unit: int,
    short_leg_lots_per_unit: int,
    position_size_multiplier: int,
) -> EntryPlan:
    """
    Build the two-leg ratio backspread plan for a GREEN or RED signal.

    Raises ValueError for FLAT direction (spec: FLAT means no trade,
    callers must not reach here with FLAT) or non-positive inputs.
    """
    if direction is Direction.FLAT:
        raise ValueError("cannot build an entry plan for FLAT direction (no trade)")
    if lot_size <= 0:
        raise ValueError(f"lot_size must be positive, got {lot_size}")
    if position_size_multiplier <= 0:
        raise ValueError(
            f"position_size_multiplier must be positive, got {position_size_multiplier}"
        )

    option_type = OptionType.CE if direction is Direction.GREEN else OptionType.PE

    long_lots = long_leg_lots_per_unit * position_size_multiplier
    short_lots = short_leg_lots_per_unit * position_size_multiplier

    legs = (
        Leg(
            role=LegRole.LONG_ATM,
            option_type=option_type,
            strike=atm_strike,
            expiry=expiry,
            lots=long_lots,
            lot_size=lot_size,
            quantity=long_lots * lot_size,
        ),
        Leg(
            role=LegRole.SHORT_OTM,
            option_type=option_type,
            strike=otm_strike,
            expiry=expiry,
            lots=short_lots,
            lot_size=lot_size,
            quantity=short_lots * lot_size,
        ),
    )

    return EntryPlan(
        direction=direction,
        atm_strike=atm_strike,
        otm_strike=otm_strike,
        expiry=expiry,
        legs=legs,
    )
