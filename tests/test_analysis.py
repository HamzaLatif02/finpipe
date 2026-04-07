"""
Unit tests for analysis.py.

All tests use synthetic data — no real database queries, no disk I/O,
no yfinance calls.  db.query_prices and cleaner.load_clean are patched
in every test so the real SQLite database is never touched.
"""
import math

import numpy as np
import pandas as pd
import pytest

from analysis import run_analysis


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_prices_df(close_values, dates=None):
    """Build a minimal analysis-ready DataFrame with a DatetimeIndex."""
    n = len(close_values)
    if dates is None:
        dates = pd.bdate_range("2023-01-02", periods=n)
    close = np.asarray(close_values, dtype=float)
    daily_return = pd.Series(close).pct_change().fillna(0).values * 100
    cumulative_return = (close / close[0] - 1) * 100
    return pd.DataFrame(
        {
            "Close":             close,
            "Open":              close * 0.99,
            "High":              close * 1.01,
            "Low":               close * 0.98,
            "Volume":            np.ones(n) * 1_000_000,
            "daily_return":      daily_return,
            "cumulative_return": cumulative_return,
        },
        index=dates,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_prices_df():
    """252-row random-walk DataFrame (one trading year) with positive drift."""
    np.random.seed(42)
    n = 252
    close = 100 * np.exp(np.cumsum(np.random.normal(0.0003, 0.015, n)))
    return _make_prices_df(close)


@pytest.fixture
def flat_prices_df():
    """252-row DataFrame with perfectly flat Close = 100."""
    return _make_prices_df(np.full(252, 100.0))


@pytest.fixture
def short_prices_df():
    """30-row DataFrame — insufficient for MA200 and monthly returns."""
    np.random.seed(0)
    close = 100 * np.exp(np.cumsum(np.random.normal(0, 0.01, 30)))
    return _make_prices_df(close, dates=pd.bdate_range("2023-01-02", periods=30))


@pytest.fixture
def declining_prices_df():
    """252-row DataFrame where Close falls linearly from 100 to 50."""
    close = np.linspace(100, 50, 252)
    return _make_prices_df(close)


@pytest.fixture
def monotonic_rise_df():
    """100-row DataFrame where Close rises linearly from 100 to 200."""
    close = np.linspace(100, 200, 100)
    return _make_prices_df(close, dates=pd.bdate_range("2023-01-02", periods=100))


@pytest.fixture
def sample_config():
    return {
        "symbol":     "TEST",
        "name":       "Test Asset",
        "asset_type": "Stocks",
        "currency":   "USD",
        "period":     "1y",
        "interval":   "1d",
    }


@pytest.fixture
def mock_db_query(mocker, sample_prices_df):
    """Patch db.query_prices so no real SQLite query is made."""
    return mocker.patch("db.query_prices", return_value=sample_prices_df)


@pytest.fixture
def mock_load_clean(mocker, sample_prices_df):
    """Patch cleaner.load_clean as the CSV fallback."""
    return mocker.patch("cleaner.load_clean", return_value=sample_prices_df)


# ── Summary stats ─────────────────────────────────────────────────────────────

class TestSummaryStats:

    def test_all_required_keys_present(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        stats  = result["summary_stats"]
        for key in [
            "total_return_pct", "annualised_return_pct", "volatility_pct",
            "sharpe_ratio", "max_drawdown_pct", "best_day_pct",
            "worst_day_pct", "start_date", "end_date",
        ]:
            assert key in stats, f"Missing key: {key}"

    def test_total_return_is_finite_number(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        val    = result["summary_stats"]["total_return_pct"]
        assert isinstance(val, float)
        assert not math.isnan(val)

    def test_total_return_negative_for_declining_prices(
        self, mocker, declining_prices_df, mock_load_clean, sample_config
    ):
        mocker.patch("db.query_prices", return_value=declining_prices_df)
        result = run_analysis(sample_config)
        assert result["summary_stats"]["total_return_pct"] < 0

    def test_total_return_zero_for_flat_prices(
        self, mocker, flat_prices_df, mock_load_clean, sample_config
    ):
        mocker.patch("db.query_prices", return_value=flat_prices_df)
        result = run_analysis(sample_config)
        assert result["summary_stats"]["total_return_pct"] == pytest.approx(0.0, abs=0.01)

    def test_volatility_zero_for_flat_prices(
        self, mocker, flat_prices_df, mock_load_clean, sample_config
    ):
        mocker.patch("db.query_prices", return_value=flat_prices_df)
        result = run_analysis(sample_config)
        assert result["summary_stats"]["volatility_pct"] == pytest.approx(0.0, abs=0.01)

    def test_max_drawdown_zero_for_monotonic_rise(
        self, mocker, monotonic_rise_df, mock_load_clean, sample_config
    ):
        mocker.patch("db.query_prices", return_value=monotonic_rise_df)
        result = run_analysis(sample_config)
        assert result["summary_stats"]["max_drawdown_pct"] == pytest.approx(0.0, abs=0.01)

    def test_max_drawdown_negative_for_declining_prices(
        self, mocker, declining_prices_df, mock_load_clean, sample_config
    ):
        mocker.patch("db.query_prices", return_value=declining_prices_df)
        result = run_analysis(sample_config)
        assert result["summary_stats"]["max_drawdown_pct"] < 0

    def test_best_day_gte_worst_day(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        stats  = result["summary_stats"]
        assert stats["best_day_pct"] >= stats["worst_day_pct"]

    def test_start_date_before_end_date(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        stats  = result["summary_stats"]
        assert stats["start_date"] < stats["end_date"]

    def test_annualised_return_is_finite(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        ann    = result["summary_stats"]["annualised_return_pct"]
        assert ann is not None
        assert not math.isnan(ann)

    def test_sharpe_none_when_volatility_zero(
        self, mocker, flat_prices_df, mock_load_clean, sample_config
    ):
        """When volatility is 0, Sharpe ratio must be None (not a division error)."""
        mocker.patch("db.query_prices", return_value=flat_prices_df)
        result = run_analysis(sample_config)
        # vol = 0 → sharpe must be None to avoid division by zero
        assert result["summary_stats"]["sharpe_ratio"] is None


# ── Moving averages ───────────────────────────────────────────────────────────

class TestMovingAverages:

    def test_ma20_column_present_with_sufficient_data(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        assert result["moving_averages"] is not None
        assert "ma_20" in result["moving_averages"].columns

    def test_ma200_all_nan_with_insufficient_data(
        self, mocker, short_prices_df, mock_load_clean, sample_config
    ):
        """MA200 column should be all NaN when fewer than 200 rows exist."""
        mocker.patch("db.query_prices", return_value=short_prices_df)
        result = run_analysis(sample_config)
        ma = result["moving_averages"]
        assert ma is not None
        assert "ma_200" in ma.columns
        assert ma["ma_200"].isna().all()

    def test_moving_averages_same_length_as_price_series(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        assert len(result["moving_averages"]) == len(result["price_series"])

    def test_ma20_non_null_from_row_20_onwards(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        """First 19 values of MA20 are NaN; from row 20 onwards they are finite."""
        result = run_analysis(sample_config)
        ma20   = result["moving_averages"]["ma_20"]
        assert ma20.iloc[:19].isna().all()
        assert ma20.iloc[19:].notna().all()


# ── Monthly returns ───────────────────────────────────────────────────────────

class TestMonthlyReturns:

    def test_monthly_returns_none_with_short_data(
        self, mocker, short_prices_df, mock_load_clean, sample_config
    ):
        """Fewer than 60 rows → monthly_returns is None."""
        mocker.patch("db.query_prices", return_value=short_prices_df)
        result = run_analysis(sample_config)
        assert result["monthly_returns"] is None

    def test_monthly_returns_is_dataframe_with_sufficient_data(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        assert isinstance(result["monthly_returns"], pd.DataFrame)

    def test_monthly_returns_columns_are_month_abbreviations(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        """Columns should be 3-letter month abbreviations like 'Jan', 'Feb'."""
        result = run_analysis(sample_config)
        mr = result["monthly_returns"]
        valid_months = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}
        for col in mr.columns:
            assert col in valid_months, f"Unexpected column: {col}"


# ── Drawdown series ───────────────────────────────────────────────────────────

class TestDrawdown:

    def test_drawdown_series_is_not_none(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        assert result["drawdown_series"] is not None

    def test_drawdown_values_all_non_positive(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        """Drawdown is always <= 0 — it can never be positive."""
        dd = run_analysis(sample_config)["drawdown_series"]
        assert (dd <= 0).all()

    def test_drawdown_zero_for_monotonic_rise(
        self, mocker, monotonic_rise_df, mock_load_clean, sample_config
    ):
        mocker.patch("db.query_prices", return_value=monotonic_rise_df)
        dd = run_analysis(sample_config)["drawdown_series"]
        assert dd.abs().max() == pytest.approx(0.0, abs=0.001)

    def test_drawdown_reaches_minus_50_for_halving_price(
        self, mocker, declining_prices_df, mock_load_clean, sample_config
    ):
        """Price halving → max drawdown near -50 %."""
        mocker.patch("db.query_prices", return_value=declining_prices_df)
        dd = run_analysis(sample_config)["drawdown_series"]
        assert dd.min() == pytest.approx(-50.0, abs=1.0)


# ── Output structure ──────────────────────────────────────────────────────────

class TestOutputStructure:

    def test_all_required_top_level_keys_present(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        for key in [
            "summary_stats", "price_series", "moving_averages",
            "monthly_returns", "drawdown_series", "asset_info", "config",
        ]:
            assert key in result, f"Missing key: {key}"

    def test_config_passed_through_unchanged(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        result = run_analysis(sample_config)
        assert result["config"]["symbol"] == "TEST"
        assert result["config"]["period"] == "1y"

    def test_price_series_is_the_loaded_dataframe(
        self, mock_db_query, mock_load_clean, sample_config, sample_prices_df
    ):
        """price_series should be the DataFrame returned by _load_prices."""
        result = run_analysis(sample_config)
        pd.testing.assert_frame_equal(result["price_series"], sample_prices_df)

    def test_analysis_returns_empty_asset_info_when_file_absent(
        self, mock_db_query, mock_load_clean, sample_config
    ):
        """When no info JSON file exists, asset_info is {} and no exception raised."""
        result = run_analysis(sample_config)
        assert result is not None
        assert result["asset_info"] == {}

    def test_db_fallback_to_clean_csv_on_empty_result(
        self, mocker, sample_prices_df, sample_config
    ):
        """If db.query_prices returns an empty DataFrame, cleaner.load_clean is used."""
        mocker.patch("db.query_prices", return_value=pd.DataFrame())
        mocker.patch("cleaner.load_clean", return_value=sample_prices_df)
        result = run_analysis(sample_config)
        assert result["summary_stats"] is not None

    def test_summary_stats_none_on_catastrophic_data_error(
        self, mocker, sample_config
    ):
        """If both DB and CSV fail, summary_stats is None but no exception propagates."""
        empty = pd.DataFrame({"Close": [], "daily_return": []})
        mocker.patch("db.query_prices", return_value=empty)
        mocker.patch("cleaner.load_clean", return_value=empty)
        result = run_analysis(sample_config)
        assert result is not None
        # With empty data, summary_stats will be None (exception caught internally)
        assert result["summary_stats"] is None

    def test_db_exception_falls_back_to_clean_csv(
        self, mocker, sample_prices_df, sample_config
    ):
        """When db.query_prices raises, cleaner.load_clean is used as fallback."""
        mocker.patch("db.query_prices", side_effect=Exception("DB connection error"))
        mocker.patch("cleaner.load_clean", return_value=sample_prices_df)
        result = run_analysis(sample_config)
        assert result["summary_stats"] is not None

    def test_moving_averages_none_when_compute_raises(
        self, mocker, mock_db_query, mock_load_clean, sample_config
    ):
        """If _compute_moving_averages raises, result['moving_averages'] is None."""
        mocker.patch(
            "analysis._compute_moving_averages",
            side_effect=Exception("MA computation error"),
        )
        result = run_analysis(sample_config)
        assert result["moving_averages"] is None

    def test_monthly_returns_none_when_compute_raises(
        self, mocker, mock_db_query, mock_load_clean, sample_config
    ):
        """If _compute_monthly_returns raises, result['monthly_returns'] is None."""
        mocker.patch(
            "analysis._compute_monthly_returns",
            side_effect=Exception("Monthly returns error"),
        )
        result = run_analysis(sample_config)
        assert result["monthly_returns"] is None

    def test_drawdown_series_none_when_compute_raises(
        self, mocker, mock_db_query, mock_load_clean, sample_config
    ):
        """If _compute_drawdown_series raises, result['drawdown_series'] is None."""
        mocker.patch(
            "analysis._compute_drawdown_series",
            side_effect=Exception("Drawdown error"),
        )
        result = run_analysis(sample_config)
        assert result["drawdown_series"] is None

    def test_info_json_loaded_when_file_exists(
        self, mocker, mock_db_query, mock_load_clean, sample_config
    ):
        """If the info JSON file exists, asset_info is populated from it."""
        import json
        from unittest.mock import mock_open, patch, MagicMock
        fake_info = {"longName": "Test Corp", "currency": "USD"}
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mocker.patch("analysis.Path", return_value=mock_path)
        mocker.patch("builtins.open", mock_open(read_data=json.dumps(fake_info)))
        result = run_analysis(sample_config)
        assert result["asset_info"] == fake_info
