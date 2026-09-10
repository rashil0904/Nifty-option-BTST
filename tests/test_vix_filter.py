from strategy.vix_filter import should_skip_day


def test_vix_below_range_does_not_skip():
    assert should_skip_day(16.99) is False


def test_vix_above_range_does_not_skip():
    assert should_skip_day(19.01) is False


def test_vix_mid_range_skips():
    assert should_skip_day(18.0) is True


def test_vix_at_lower_boundary_inclusive_skips():
    assert should_skip_day(17.0) is True


def test_vix_at_upper_boundary_inclusive_skips():
    assert should_skip_day(19.0) is True


def test_vix_just_below_lower_boundary_does_not_skip():
    assert should_skip_day(16.999999) is False


def test_vix_just_above_upper_boundary_does_not_skip():
    assert should_skip_day(19.000001) is False
