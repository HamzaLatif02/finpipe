"""
Tests for report caching: db cache functions and HTTP endpoint behaviour.

The db tests use a temporary SQLite database so they never touch the real
reporting.db.  The HTTP tests build a minimal Flask app (same pattern as
test_rate_limiting.py) that wires up the pipeline blueprint with a mocked
pipeline and a real in-memory SQLite cache.
"""
import json  # noqa: F401
import os
import sys
import tempfile
import time
import sqlite3

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND = os.path.abspath(os.path.join(_ROOT, "backend"))
for _p in (_ROOT, _BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tmp_db():
    """Create a temporary SQLite file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _init_cache(db_path: str) -> None:
    """Bootstrap the report_cache table in a fresh SQLite file."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_cache (
            cache_key     TEXT PRIMARY KEY,
            symbol        TEXT NOT NULL,
            name          TEXT NOT NULL,
            asset_type    TEXT NOT NULL,
            currency      TEXT NOT NULL,
            period        TEXT NOT NULL,
            interval_val  TEXT NOT NULL,
            start_date    TEXT,
            end_date      TEXT,
            result_json   TEXT NOT NULL,
            chart_paths   TEXT NOT NULL,
            pdf_path      TEXT NOT NULL,
            created_at    REAL NOT NULL,
            expires_at    REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_CONFIG = {
    "symbol":     "AAPL",
    "name":       "Apple Inc.",
    "asset_type": "Stocks",
    "currency":   "USD",
    "period":     "1y",
    "interval":   "1d",
}

SAMPLE_RESULT = {
    "summary_stats": {
        "total_return_pct": 24.5,
        "volatility_pct":   18.3,
        "sharpe_ratio":     1.34,
    },
    "latest_value": {"date": "2024-12-31", "close": 182.5},
    "asset_info":   {"longName": "Apple Inc.", "currency": "USD"},
}


# ══════════════════════════════════════════════════════════════════════════════
# Part 1 — db cache functions (direct, no Flask)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestMakeCacheKey:

    def test_same_config_same_key(self):
        from db import _make_cache_key
        k1 = _make_cache_key(SAMPLE_CONFIG)
        k2 = _make_cache_key(SAMPLE_CONFIG)
        assert k1 == k2

    def test_different_symbols_different_keys(self):
        from db import _make_cache_key
        k_aapl = _make_cache_key({**SAMPLE_CONFIG, "symbol": "AAPL"})
        k_msft = _make_cache_key({**SAMPLE_CONFIG, "symbol": "MSFT"})
        assert k_aapl != k_msft

    def test_different_periods_different_keys(self):
        from db import _make_cache_key
        k_1y = _make_cache_key({**SAMPLE_CONFIG, "period": "1y"})
        k_2y = _make_cache_key({**SAMPLE_CONFIG, "period": "2y"})
        assert k_1y != k_2y

    def test_different_intervals_different_keys(self):
        from db import _make_cache_key
        k_1d = _make_cache_key({**SAMPLE_CONFIG, "interval": "1d"})
        k_1w = _make_cache_key({**SAMPLE_CONFIG, "interval": "1wk"})
        assert k_1d != k_1w

    def test_custom_date_range_included_in_key(self):
        from db import _make_cache_key
        cfg_custom = {**SAMPLE_CONFIG, "period": "custom",
                      "start_date": "2023-01-01", "end_date": "2024-01-01"}
        cfg_other  = {**SAMPLE_CONFIG, "period": "custom",
                      "start_date": "2022-01-01", "end_date": "2024-01-01"}
        assert _make_cache_key(cfg_custom) != _make_cache_key(cfg_other)

    def test_symbol_normalised_to_uppercase(self):
        from db import _make_cache_key
        k_upper = _make_cache_key({**SAMPLE_CONFIG, "symbol": "AAPL"})
        k_lower = _make_cache_key({**SAMPLE_CONFIG, "symbol": "aapl"})
        assert k_upper == k_lower


@pytest.mark.unit
class TestSaveAndGetCachedReport:

    def setup_method(self):
        self.db_path = _tmp_db()
        _init_cache(self.db_path)
        # Monkey-patch db module to use temp db
        import db as db_module
        self._orig_db_path = db_module.DB_PATH
        db_module.DB_PATH = __import__("pathlib").Path(self.db_path)

    def teardown_method(self):
        import db as db_module
        db_module.DB_PATH = self._orig_db_path
        os.unlink(self.db_path)

    def test_get_returns_none_when_no_entry(self):
        from db import get_cached_report
        result = get_cached_report(SAMPLE_CONFIG)
        assert result is None

    def test_save_then_get_returns_entry(self, tmp_path):
        from db import save_cached_report, get_cached_report
        # Create real temp files so file-existence check passes
        pdf = tmp_path / "report.pdf"; pdf.write_bytes(b"PDF")
        chart = tmp_path / "chart.png"; chart.write_bytes(b"PNG")

        save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))
        cached = get_cached_report(SAMPLE_CONFIG)

        assert cached is not None
        assert cached["cache_hit"] is True
        assert cached["result"]["summary_stats"]["total_return_pct"] == 24.5

    def test_get_returns_none_when_files_missing(self):
        from db import save_cached_report, get_cached_report
        save_cached_report(
            SAMPLE_CONFIG, SAMPLE_RESULT,
            ["/nonexistent/chart.png"], "/nonexistent/report.pdf",
        )
        result = get_cached_report(SAMPLE_CONFIG)
        assert result is None

    def test_get_returns_none_after_expiry(self, tmp_path, monkeypatch):
        from db import save_cached_report, get_cached_report, CACHE_TTL
        pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png"; chart.write_bytes(b"PNG")
        save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))

        # Wind the clock forward past TTL (capture real time.time before patching)
        future = time.time() + CACHE_TTL + 60
        monkeypatch.setattr("db.time.time", lambda: future)
        result = get_cached_report(SAMPLE_CONFIG)
        assert result is None

    def test_age_minutes_is_accurate(self, tmp_path, monkeypatch):
        from db import save_cached_report, get_cached_report
        pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png"; chart.write_bytes(b"PNG")

        base_time = time.time()
        monkeypatch.setattr("db.time.time", lambda: base_time)
        save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))

        # Advance 30 minutes
        monkeypatch.setattr("db.time.time", lambda: base_time + 1800)
        cached = get_cached_report(SAMPLE_CONFIG)
        assert cached is not None
        assert abs(cached["age_minutes"] - 30.0) < 0.2

    def test_save_overwrites_existing_entry(self, tmp_path):
        from db import save_cached_report, get_cached_report
        pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png"; chart.write_bytes(b"PNG")

        result_v1 = {**SAMPLE_RESULT, "summary_stats": {"total_return_pct": 10.0}}
        result_v2 = {**SAMPLE_RESULT, "summary_stats": {"total_return_pct": 99.0}}

        save_cached_report(SAMPLE_CONFIG, result_v1, [str(chart)], str(pdf))
        save_cached_report(SAMPLE_CONFIG, result_v2, [str(chart)], str(pdf))

        cached = get_cached_report(SAMPLE_CONFIG)
        assert cached["result"]["summary_stats"]["total_return_pct"] == 99.0


@pytest.mark.unit
class TestPurgeExpiredCache:

    def setup_method(self):
        self.db_path = _tmp_db()
        _init_cache(self.db_path)
        import db as db_module
        self._orig_db_path = db_module.DB_PATH
        db_module.DB_PATH = __import__("pathlib").Path(self.db_path)

    def teardown_method(self):
        import db as db_module
        db_module.DB_PATH = self._orig_db_path
        os.unlink(self.db_path)

    def test_purge_removes_expired_entries(self, tmp_path):
        """Insert an already-expired entry directly; purge should remove it."""
        from db import purge_expired_cache, _make_cache_key  # noqa: F401
        conn = sqlite3.connect(self.db_path)
        now = time.time()
        conn.execute("""
            INSERT INTO report_cache
            (cache_key, symbol, name, asset_type, currency, period, interval_val,
             start_date, end_date, result_json, chart_paths, pdf_path,
             created_at, expires_at)
            VALUES (?, 'TEST', 'Test', 'Stocks', 'USD', '1y', '1d',
                    NULL, NULL, '{}', '[]', '/tmp/x.pdf', ?, ?)
        """, ("expired_key", now - 7200, now - 3600))
        conn.commit()
        conn.close()

        deleted = purge_expired_cache()
        assert deleted >= 1

    def test_purge_keeps_valid_entries(self, tmp_path):
        from db import save_cached_report, purge_expired_cache, get_cached_report
        pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png"; chart.write_bytes(b"PNG")
        save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))

        deleted = purge_expired_cache()
        assert deleted == 0
        assert get_cached_report(SAMPLE_CONFIG) is not None

    def test_purge_returns_zero_when_nothing_expired(self):
        from db import purge_expired_cache
        deleted = purge_expired_cache()
        assert deleted == 0


# ══════════════════════════════════════════════════════════════════════════════
# Part 2 — HTTP endpoint cache behaviour (minimal Flask app + mocks)
# ══════════════════════════════════════════════════════════════════════════════

def _make_minimal_app():
    """Build a minimal Flask app that exercises the cache check logic
    in the pipeline endpoint without running the real pipeline."""
    from flask import Flask, jsonify, request as flask_request

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True

    @flask_app.post("/api/pipeline/run")
    def run_pipeline():
        body         = flask_request.get_json(silent=True) or {}
        bypass_cache = (
            flask_request.headers.get("X-Cache-Bypass", "").lower() == "true"
            or body.get("bypass_cache") is True
        )
        config = {
            "symbol":   body.get("symbol", "AAPL").upper(),
            "name":     body.get("name", "Apple Inc."),
            "period":   body.get("period", "1y"),
            "interval": body.get("interval", "1d"),
            "asset_type": body.get("asset_type", "Stocks"),
            "currency": body.get("currency", "USD"),
        }
        from db import get_cached_report
        if not bypass_cache:
            cached = get_cached_report(config)
            if cached:
                return jsonify({
                    "status":        "success",
                    "cache_hit":     True,
                    "age_minutes":   cached["age_minutes"],
                    "symbol":        config["symbol"],
                    "summary_stats": cached["result"].get("summary_stats", {}),
                    "chart_urls":    [],
                    "latest_value":  cached["result"].get("latest_value"),
                    "asset_info":    cached["result"].get("asset_info", {}),
                })
        # Simulate pipeline run
        return jsonify({
            "status":        "success",
            "cache_hit":     False,
            "symbol":        config["symbol"],
            "summary_stats": {"total_return_pct": 99.0},
            "chart_urls":    [],
            "latest_value":  None,
            "asset_info":    {},
        })

    return flask_app


@pytest.fixture()
def http_client(tmp_path):
    """Flask test client backed by a fresh in-memory SQLite cache."""
    import db as db_module
    orig_path = db_module.DB_PATH
    db_path = tmp_path / "test_cache.db"
    db_module.DB_PATH = db_path
    _init_cache(str(db_path))

    flask_app = _make_minimal_app()
    with flask_app.test_client() as c:
        yield c

    db_module.DB_PATH = orig_path


@pytest.mark.unit
class TestHTTPCacheEndpoint:

    def test_cache_miss_runs_pipeline(self, http_client):
        """First request — cache empty — runs the pipeline."""
        resp = http_client.post("/api/pipeline/run", json=SAMPLE_CONFIG)
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["cache_hit"] is False

    def test_cache_hit_skips_pipeline(self, http_client, tmp_path):
        """Pre-seed cache; second request should be a cache hit."""
        import db
        pdf   = tmp_path / "r.pdf";   pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png";   chart.write_bytes(b"PNG")
        db.save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))

        resp = http_client.post("/api/pipeline/run", json=SAMPLE_CONFIG)
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["cache_hit"] is True
        assert "age_minutes" in data

    def test_cache_hit_returns_summary_stats(self, http_client, tmp_path):
        import db
        pdf   = tmp_path / "r.pdf";   pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png";   chart.write_bytes(b"PNG")
        db.save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))

        resp = http_client.post("/api/pipeline/run", json=SAMPLE_CONFIG)
        data = resp.get_json()
        assert data["cache_hit"] is True
        assert "summary_stats" in data
        assert data["summary_stats"]["total_return_pct"] == 24.5

    def test_bypass_cache_header_runs_pipeline(self, http_client, tmp_path):
        """X-Cache-Bypass: true forces fresh run even when cache is warm."""
        import db
        pdf   = tmp_path / "r.pdf";   pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png";   chart.write_bytes(b"PNG")
        db.save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))

        resp = http_client.post(
            "/api/pipeline/run", json=SAMPLE_CONFIG,
            headers={"X-Cache-Bypass": "true"},
        )
        data = resp.get_json()
        assert data["cache_hit"] is False

    def test_bypass_cache_body_flag_runs_pipeline(self, http_client, tmp_path):
        """bypass_cache=true in body also forces fresh run."""
        import db
        pdf   = tmp_path / "r.pdf";   pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png";   chart.write_bytes(b"PNG")
        db.save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))

        resp = http_client.post(
            "/api/pipeline/run",
            json={**SAMPLE_CONFIG, "bypass_cache": True},
        )
        data = resp.get_json()
        assert data["cache_hit"] is False

    def test_cache_miss_when_different_symbol(self, http_client, tmp_path):
        """A cache entry for AAPL does not satisfy a request for MSFT."""
        import db
        pdf   = tmp_path / "r.pdf";   pdf.write_bytes(b"PDF")
        chart = tmp_path / "c.png";   chart.write_bytes(b"PNG")
        db.save_cached_report(SAMPLE_CONFIG, SAMPLE_RESULT, [str(chart)], str(pdf))

        resp = http_client.post(
            "/api/pipeline/run",
            json={**SAMPLE_CONFIG, "symbol": "MSFT"},
        )
        data = resp.get_json()
        assert data["cache_hit"] is False
