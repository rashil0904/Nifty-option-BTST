from datetime import date

from strategy.expiry import compute_entry_expiry

TUESDAY = 1  # date.weekday() numbering


def test_monday_uses_this_weeks_tuesday():
    # 2026-09-07 is a Monday; nearest Tuesday is tomorrow, not today.
    assert compute_entry_expiry(date(2026, 9, 7), TUESDAY) == date(2026, 9, 8)


def test_wednesday_uses_next_weeks_tuesday():
    # 2026-09-09 is a Wednesday; nearest Tuesday is 6 days out.
    assert compute_entry_expiry(date(2026, 9, 9), TUESDAY) == date(2026, 9, 15)


def test_on_expiry_day_itself_rolls_to_next_week():
    # 2026-09-08 is a Tuesday (today IS expiry) -> must roll forward,
    # never trade a contract expiring same-day.
    assert compute_entry_expiry(date(2026, 9, 8), TUESDAY) == date(2026, 9, 15)


def test_day_after_expiry_uses_next_weeks_tuesday():
    # 2026-09-10 is a Thursday, right after Tuesday's expiry.
    assert compute_entry_expiry(date(2026, 9, 10), TUESDAY) == date(2026, 9, 15)
