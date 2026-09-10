"""
Strategy configuration constants. No I/O, no broker calls.

These values encode the strategy spec as given. Anything marked
"CONFIRM BEFORE LIVE" is a place where the spec depends on an external
fact (exchange rules, broker behavior) that should be re-verified
against live/broker data before this trades real capital.
"""

# --- VIX filter -------------------------------------------------------
# Skip the trading day entirely if India VIX (checked once, at 15:15)
# falls in this inclusive range.
VIX_SKIP_LOW = 17.0
VIX_SKIP_HIGH = 19.0

# --- Direction signal ---------------------------------------------------
# Nifty Future 15:14 candle close vs Nifty Future 09:15 candle open.
# CONFIRM BEFORE LIVE: verify the data source's candle-labeling convention
# (does "15:14 candle" mean the candle timestamped 15:14:00 covering
# 15:14:00-15:15:00?) against a known historical value before trusting
# this signal live. This module only implements the comparison; reading
# the actual candle is a broker-layer concern (not built yet).

# --- Strike selection -----------------------------------------------------
# OTM leg is ATM +/- this many points, then snapped to the nearest valid
# strike interval (interval itself must be resolved at runtime from the
# instrument master -- never hardcoded here).
OTM_OFFSET_POINTS = 300

# --- Ratio backspread structure ---------------------------------------
# 2:1 ratio: BUY this many lots ATM, SELL this many lots OTM, per "unit"
# of the position.
LONG_LEG_LOTS_PER_UNIT = 2
SHORT_LEG_LOTS_PER_UNIT = 1

# Number of ratio-units to trade per signal. Confirm with user before
# changing from 1.
POSITION_SIZE_MULTIPLIER = 1

# --- Expiry ---------------------------------------------------------------
# Nifty weekly expiry weekday, Python `date.weekday()` numbering
# (Monday=0 ... Sunday=6). Tuesday=1.
# CONFIRM BEFORE LIVE: NSE moved Nifty weekly expiry from Thursday to
# Tuesday effective Sep 2025. Re-verify this is still the live expiry
# weekday before relying on it -- exchanges have changed this before and
# may again.
WEEKLY_EXPIRY_WEEKDAY = 1  # Tuesday

# --- Exit -------------------------------------------------------------
# Unconditional square-off time, next trading day, IST. No P&L check.
# There is deliberately NO stop loss anywhere in this strategy.
EXIT_TIME_HOUR = 9
EXIT_TIME_MINUTE = 18

# --- Entry ---------------------------------------------------------------
ENTRY_TIME_HOUR = 15
ENTRY_TIME_MINUTE = 15
