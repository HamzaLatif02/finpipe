import math
from unittest.mock import patch

import pandas as pd
import pytest

import cleaner


def _make_prices(*rows):
    """Build a minimal OHLCV DataFrame from (date_str, open, high, low, close, volume) tuples."""
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    return df


def _run_clean(df, symbol="TEST"):
    """Patch fetcher.load_raw with a synthetic DataFrame and call clean_data."""
    config = {"symbol": symbol}
    with patch("cleaner.fetcher.load_raw", return_value={"prices": df}), \
         patch("cleaner.CLEAN_DIR") as mock_dir:
        # Prevent any disk writes during tests.
        mock_dir.__truediv__ = lambda self, other: mock_dir
        mock_dir.mkdir = lambda **kw: None
        mock_dir.__str__ = lambda self: "data/clean"

        # Intercept to_csv on the returned DataFrame by patching at the class level.
        with patch.object(pd.DataFrame, "to_csv"):
            return cleaner.clean_data(config)


# ---------------------------------------------------------------------------
# 1. Rows with null Close values are dropped
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_null_close_rows_dropped():
    df = _make_prices(
        ("2024-01-01", 100, 105, 98, 102, 1000),
        ("2024-01-02", 102, 107, 101, None, 1100),   # null Close — should be dropped
        ("2024-01-03", 103, 108, 102, 106, 1200),
    )
    result = _run_clean(df)
    assert len(result) == 2
    assert pd.Timestamp("2024-01-02") not in result["Date"].values


# ---------------------------------------------------------------------------
# 2. Rows with zero Close values are dropped
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_zero_close_rows_dropped():
    df = _make_prices(
        ("2024-01-01", 100, 105, 98,  102, 1000),
        ("2024-01-02", 0,   0,   0,   0,   0),       # zero Close — should be dropped
        ("2024-01-03", 103, 108, 102, 106, 1200),
    )
    result = _run_clean(df)
    assert len(result) == 2
    assert 0.0 not in result["Close"].values


# ---------------------------------------------------------------------------
# 3. Duplicate dates are removed — last occurrence kept
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_duplicate_dates_last_kept():
    df = _make_prices(
        ("2024-01-01", 100, 105, 98,  102, 1000),
        ("2024-01-02", 102, 107, 101, 104, 1100),   # first occurrence of Jan 2
        ("2024-01-02", 102, 109, 101, 108, 1300),   # duplicate — this one should survive
        ("2024-01-03", 103, 108, 102, 106, 1200),
    )
    result = _run_clean(df)
    assert len(result) == 3
    jan2_close = result.loc[result["Date"] == pd.Timestamp("2024-01-02"), "Close"].iloc[0]
    assert jan2_close == pytest.approx(108.0)


# ---------------------------------------------------------------------------
# 4. daily_return is computed correctly (spot-check second row)
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_daily_return_spot_check():
    df = _make_prices(
        ("2024-01-01", 100, 105, 98,  100, 1000),
        ("2024-01-02", 100, 107, 99,  110, 1100),   # +10% from 100 → 110
        ("2024-01-03", 110, 115, 108, 121, 1200),   # +10% from 110 → 121
    )
    result = _run_clean(df)
    assert math.isnan(result["daily_return"].iloc[0])          # first row is always NaN
    assert result["daily_return"].iloc[1] == pytest.approx(10.0, rel=1e-4)
    assert result["daily_return"].iloc[2] == pytest.approx(10.0, rel=1e-4)


# ---------------------------------------------------------------------------
# 5. cumulative_return starts at 0.0 for the first row
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_cumulative_return_starts_at_zero():
    df = _make_prices(
        ("2024-01-01", 100, 105, 98,  100, 1000),
        ("2024-01-02", 100, 110, 99,  120, 1100),
        ("2024-01-03", 120, 125, 118, 150, 1200),
    )
    result = _run_clean(df)
    assert result["cumulative_return"].iloc[0] == pytest.approx(0.0)
    assert result["cumulative_return"].iloc[1] == pytest.approx(20.0, rel=1e-4)
    assert result["cumulative_return"].iloc[2] == pytest.approx(50.0, rel=1e-4)


# ---------------------------------------------------------------------------
# 6. Output is sorted by Date ascending
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_output_sorted_ascending():
    df = _make_prices(
        ("2024-01-03", 103, 108, 102, 106, 1200),   # intentionally out of order
        ("2024-01-01", 100, 105, 98,  102, 1000),
        ("2024-01-02", 102, 107, 101, 104, 1100),
    )
    result = _run_clean(df)
    dates = result["Date"].tolist()
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# 7. vwap is skipped gracefully when Volume is all zeros
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_vwap_skipped_when_volume_zero():
    df = _make_prices(
        ("2024-01-01", 100, 105, 98,  102, 0),
        ("2024-01-02", 102, 107, 101, 104, 0),
        ("2024-01-03", 103, 108, 102, 106, 0),
    )
    result = _run_clean(df)
    assert "vwap" not in result.columns
