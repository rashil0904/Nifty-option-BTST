"""VIX day-skip filter. Pure logic, no I/O."""

from config import VIX_SKIP_HIGH, VIX_SKIP_LOW


def should_skip_day(vix_value: float) -> bool:
    """
    Return True if the trading day should be skipped entirely.

    Per spec: skip if India VIX is in [VIX_SKIP_LOW, VIX_SKIP_HIGH]
    inclusive, as read once at 15:15.
    """
    return VIX_SKIP_LOW <= vix_value <= VIX_SKIP_HIGH
