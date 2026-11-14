from datetime import date

import pytest

from matrix import analytics as a


def series(values, start=date(2020, 1, 1), step_days=1):
    from datetime import timedelta
    return [(start + timedelta(days=i * step_days), v) for i, v in enumerate(values)]


def test_value_on_or_before():
    s = series([10, 11, 12])
    assert a.value_on_or_before(s, date(2020, 1, 2)) == 11
    assert a.value_on_or_before(s, date(2019, 12, 31)) is None
    assert a.value_on_or_before(s, date(2030, 1, 1)) == 12


def test_trailing_return_and_cagr():
    # 100 -> 121 over exactly 2 years = 10% a year
    s = [(date(2020, 1, 1), 100.0), (date(2022, 1, 1), 121.0)]
    assert a.trailing_return(s, years=2) == pytest.approx(0.10, abs=1e-3)
    assert a.trailing_return(s, years=5) is None  # not enough history


def test_trailing_return_under_one_year_is_absolute():
    s = [(date(2020, 1, 1), 100.0), (date(2020, 7, 1), 110.0)]
    assert a.trailing_return(s, years=0.5) == pytest.approx(0.10)


def test_max_drawdown():
    s = series([100, 120, 60, 90, 130])
    assert a.max_drawdown(s) == pytest.approx(-0.5)  # 120 -> 60


def test_volatility_zero_for_flat_and_positive_for_moving():
    assert a.volatility(series([10] * 30)) == 0
    assert a.volatility(series([10, 11] * 15)) > 0
    assert a.volatility(series([10, 11])) is None  # too few points


def test_xirr_simple_one_year_doubling():
    flows = [(date(2021, 1, 1), -100), (date(2022, 1, 1), 200)]  # 365-day year
    assert a.xirr(flows) == pytest.approx(1.0, abs=1e-4)


def test_xirr_multiple_flows_matches_known_value():
    # Invest 1000 then 1000 six months later, worth 2200 after a year.
    flows = [(date(2020, 1, 1), -1000), (date(2020, 7, 1), -1000), (date(2021, 1, 1), 2200)]
    r = a.xirr(flows)
    npv = sum(cf / (1 + r) ** ((d - date(2020, 1, 1)).days / 365) for d, cf in flows)
    assert abs(npv) < 1e-6 and 0.12 < r < 0.14


def test_xirr_loss_and_invalid():
    assert a.xirr([(date(2021, 1, 1), -100), (date(2022, 1, 1), 50)]) == pytest.approx(-0.5, abs=1e-4)
    assert a.xirr([(date(2020, 1, 1), 100)]) is None  # no outflow


def test_rolling_consistency():
    # Steadily rising: every 1-year window positive
    s = series([100 * 1.0003 ** i for i in range(800)])
    c = a.rolling_consistency(s, years=1)
    assert c["windows"] > 0 and c["positive_share"] == 1.0


def test_adjusted_series_removes_split_jump():
    # 1:2 split on day 3: raw close halves, but exchange prev_close is adjusted to 102.
    rows = [
        {"date": "2026-01-01", "close": 200.0, "prev_close": 198.0},
        {"date": "2026-01-02", "close": 204.0, "prev_close": 200.0},
        {"date": "2026-01-05", "close": 103.0, "prev_close": 102.0},
    ]
    s = a.adjusted_series(rows)
    assert [round(v, 2) for _, v in s] == [100.0, 102.0, 103.0]
    assert a.max_drawdown(s) == 0
