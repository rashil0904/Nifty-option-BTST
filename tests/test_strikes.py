import pytest

from strategy.strikes import calculate_atm_strike, calculate_otm_strike, snap_to_strike


# --- ATM rounding, interval=50 (typical Nifty grid) ---


def test_atm_rounds_down_when_closer_to_lower_strike():
    assert calculate_atm_strike(24637, 50) == 24650  # 37 away vs 13 away -> nearer strike


def test_atm_rounds_to_nearer_lower_strike():
    assert calculate_atm_strike(24612, 50) == 24600  # 12 away vs 38 away


def test_atm_exact_halfway_rounds_up():
    assert calculate_atm_strike(24625, 50) == 24650  # exactly between 24600/24650


def test_atm_already_on_grid_is_unchanged():
    assert calculate_atm_strike(24600, 50) == 24600


# --- ATM rounding, interval=100 ---


def test_atm_interval_100():
    assert calculate_atm_strike(24637, 100) == 24600


# --- OTM snapping ---


def test_otm_green_side_adds_offset():
    # ATM 24650, +300 -> 24950, already on 50-grid
    assert calculate_otm_strike(24650, 300, 50, direction_sign=1) == 24950


def test_otm_red_side_subtracts_offset():
    # ATM 24650, -300 -> 24350, already on 50-grid
    assert calculate_otm_strike(24650, 300, 50, direction_sign=-1) == 24350


def test_otm_snaps_to_grid_when_offset_lands_off_grid():
    # interval 70: ATM 700, +300 -> raw 1000, nearest 70-multiple is 980
    assert calculate_otm_strike(700, 300, 70, direction_sign=1) == 980


def test_otm_invalid_direction_sign_raises():
    with pytest.raises(ValueError):
        calculate_otm_strike(24650, 300, 50, direction_sign=0)


# --- snap_to_strike edge cases ---


def test_snap_to_strike_rejects_nonpositive_interval():
    with pytest.raises(ValueError):
        snap_to_strike(24637, 0)
    with pytest.raises(ValueError):
        snap_to_strike(24637, -50)
