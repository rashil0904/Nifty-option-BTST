"""
Weekly expiry selection with same-day rollover and holiday shift.

CONFIRM BEFORE LIVE: config.MARKET_HOLIDAYS is a manually maintained
list, not a live exchange calendar. If it's missing a holiday, this
computes an expiry date that doesn't actually exist on the exchange --
that surfaces downstream as resolve_option_instrument's
InstrumentNotFoundError, which is the signal to add the missing date
here, not a bug in this function.
"""

from datetime import date, timedelta

from config import MARKET_HOLIDAYS


def compute_entry_expiry(today: date, expiry_weekday: int, holidays: set[date] | None = None) -> date:
    """
    Return the expiry date to use for a position entered "today".

    expiry_weekday: date.weekday() numbering (Monday=0 ... Sunday=6).

    Normally this is the nearest upcoming occurrence of expiry_weekday.
    Two adjustments on top of that:
      - Holiday shift: if that date is a weekend or a market holiday,
        NSE moves the expiry to the previous trading day instead (e.g.
        a Tuesday holiday pushes expiry to Monday) -- step back a day
        at a time until landing on a real trading day.
      - Same-day guard: if the (possibly shifted) expiry lands on or
        before today, a position entered today wouldn't survive
        overnight, which this strategy requires -- roll forward to the
        next week's cycle and re-apply the holiday shift to that one.
    """
    if holidays is None:
        holidays = MARKET_HOLIDAYS

    candidate = today + timedelta(days=(expiry_weekday - today.weekday()) % 7)
    while True:
        expiry = candidate
        while expiry.weekday() >= 5 or expiry in holidays:
            expiry -= timedelta(days=1)
        if expiry > today:
            return expiry
        candidate += timedelta(days=7)
