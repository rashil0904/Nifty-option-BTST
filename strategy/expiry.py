"""
Weekly expiry selection with same-day rollover. Pure logic, no I/O.

CONFIRM BEFORE LIVE: this computes the *calendar* nearest weekly expiry
weekday. It does not know about exchange holidays -- if NSE shifts an
expiry because the computed weekday is a trading holiday, that requires
a holiday calendar (a broker/data-layer concern, not built yet). Do not
trust this function's output blindly on weeks with holidays near expiry.
"""

from datetime import date, timedelta


def compute_entry_expiry(today: date, expiry_weekday: int) -> date:
    """
    Return the expiry date to use for a position entered "today".

    expiry_weekday: date.weekday() numbering (Monday=0 ... Sunday=6).

    Normally this is the nearest upcoming occurrence of expiry_weekday
    (which may be today itself). But per spec, if today IS the expiry
    day, the position must survive overnight, so we roll to NEXT week's
    expiry instead of trading a contract that expires same-day.
    """
    days_ahead = (expiry_weekday - today.weekday()) % 7
    nearest_expiry = today + timedelta(days=days_ahead)
    if nearest_expiry == today:
        nearest_expiry += timedelta(days=7)
    return nearest_expiry
