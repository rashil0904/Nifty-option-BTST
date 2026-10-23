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


def test_holiday_on_expiry_tuesday_shifts_to_monday():
    # 2026-09-15 (Tue) is a holiday -> NSE expiry moves to Monday 2026-09-14.
    holidays = {date(2026, 9, 15)}
    assert compute_entry_expiry(date(2026, 9, 9), TUESDAY, holidays=holidays) == date(2026, 9, 14)


def test_holiday_shift_landing_on_entry_day_rolls_to_next_week():
    # Same holiday as above, but entering ON the shifted date (Monday
    # 2026-09-14) itself -- the shifted expiry can't be today either
    # (must survive overnight), so it rolls to the following week's
    # Tuesday (2026-09-22, unaffected by the holiday).
    holidays = {date(2026, 9, 15)}
    assert compute_entry_expiry(date(2026, 9, 14), TUESDAY, holidays=holidays) == date(2026, 9, 22)


def test_holiday_shift_landing_before_entry_day_rolls_to_next_week():
    # Entering Wednesday 2026-09-16, the week whose Tuesday (09-15) was
    # the holiday is already over -- next occurrence is next Tuesday
    # 2026-09-22, which isn't a holiday.
    holidays = {date(2026, 9, 15)}
    assert compute_entry_expiry(date(2026, 9, 16), TUESDAY, holidays=holidays) == date(2026, 9, 22)


def test_two_consecutive_holidays_shift_back_two_days():
    # Both Tuesday and Monday of expiry week are holidays -> shifts back
    # to Friday the week before.
    holidays = {date(2026, 9, 15), date(2026, 9, 14)}
    assert compute_entry_expiry(date(2026, 9, 9), TUESDAY, holidays=holidays) == date(2026, 9, 11)
