from strategy.direction import Direction, determine_direction


def test_close_above_open_is_green():
    assert determine_direction(candle_1514_close=24650, open_0915=24600) is Direction.GREEN


def test_close_below_open_is_red():
    assert determine_direction(candle_1514_close=24550, open_0915=24600) is Direction.RED


def test_close_equal_open_is_flat():
    assert determine_direction(candle_1514_close=24600, open_0915=24600) is Direction.FLAT


def test_tiny_positive_difference_is_green():
    assert determine_direction(candle_1514_close=24600.05, open_0915=24600.0) is Direction.GREEN


def test_tiny_negative_difference_is_red():
    assert determine_direction(candle_1514_close=24599.95, open_0915=24600.0) is Direction.RED
