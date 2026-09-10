"""
Direction signal: Nifty Future 15:14 candle close vs 09:15 open.
Pure logic, no I/O.

CONFIRM BEFORE LIVE: this module only compares two already-fetched
price values. The caller (broker layer, not yet built) is responsible
for fetching the *correct* candle values -- verify the data source's
candle-labeling convention (does "15:14 candle" mean the 1-minute
candle timestamped 15:14:00, covering 15:14:00-15:15:00?) against a
known historical value before wiring this up to real data. Also only
call this at/after 15:15:00 so the 15:14 candle is settled, not a live
LTP tick.
"""

from enum import Enum


class Direction(Enum):
    GREEN = "GREEN"  # call side
    RED = "RED"  # put side
    FLAT = "FLAT"  # equal -> no trade


def determine_direction(candle_1514_close: float, open_0915: float) -> Direction:
    """
    GREEN if 15:14 close > 09:15 open (call side).
    RED if 15:14 close < 09:15 open (put side).
    FLAT if equal (skip, no trade).
    """
    if candle_1514_close > open_0915:
        return Direction.GREEN
    if candle_1514_close < open_0915:
        return Direction.RED
    return Direction.FLAT
