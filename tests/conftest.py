"""
Shared pytest configuration and fixtures.

Path setup and environment variables are configured here so every test file
can import pipeline modules without its own sys.path manipulation.
"""
import os
import sys

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

for _p in (ROOT, BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Environment defaults (set before any imports that read env vars) ──────────

os.environ.setdefault("ANTHROPIC_API_KEY",    "test-key")
os.environ.setdefault("RESEND_API_KEY",        "test-key")
os.environ.setdefault("DATABASE_URL",          "")
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("SECRET_KEY",            "test-secret")
os.environ.setdefault("FLASK_ENV",             "testing")


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_chart_cache():
    """Clear the chart analyst in-memory cache before and after each test."""
    try:
        from chart_analyst import _cache
        _cache.clear()
    except (ImportError, AttributeError):
        pass
    yield
    try:
        from chart_analyst import _cache
        _cache.clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture
def sample_config():
    """Standard asset config used across multiple test files."""
    return {
        "symbol":     "AAPL",
        "name":       "Apple Inc.",
        "asset_type": "Stocks",
        "currency":   "USD",
        "period":     "1y",
        "interval":   "1d",
    }


@pytest.fixture
def sample_summary_stats():
    """Realistic summary stats dict for testing."""
    return {
        "total_return_pct":      34.21,
        "annualised_return_pct": 34.21,
        "volatility_pct":        22.4,
        "sharpe_ratio":          1.52,
        "max_drawdown_pct":      -18.7,
        "best_day_pct":          4.2,
        "worst_day_pct":         -3.8,
        "start_date":            "2023-01-02",
        "end_date":              "2023-12-29",
    }
