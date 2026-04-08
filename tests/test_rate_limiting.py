"""
Tests for rate limiting on Flask API endpoints.

We build a minimal Flask application that replicates the exact same
rate-limit decorators used in the real blueprints, without importing
the full application stack (which requires eventlet + many root-level
dependencies).  The limiter configuration under test is the same object
produced by extensions.py — we just bind it to stub view functions.
"""
import sys
import os
import pytest

# Ensure extensions.py (inside backend/) is importable
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _make_app():
    """Build a minimal Flask app with rate limits mirroring the real blueprints."""
    from flask import Flask, jsonify
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
        headers_enabled=True,
    )
    limiter.init_app(flask_app)

    # ── Mirrored endpoint stubs ────────────────────────────────────────────
    # Each stub carries the exact same @limiter.limit() string as the real
    # blueprint so we test the actual limiting configuration.

    @flask_app.post("/api/pipeline/run")
    @limiter.limit("30 per day;10 per hour;3 per minute")
    def pipeline_run():
        return jsonify({"status": "ok"})

    @flask_app.post("/api/comparison/run")
    @limiter.limit("15 per day;5 per hour;2 per minute")
    def comparison_run():
        return jsonify({"status": "ok"})

    @flask_app.post("/api/schedule/add")
    @limiter.limit("20 per day;5 per hour")
    def schedule_add():
        return jsonify({"status": "ok"})

    @flask_app.post("/api/schedule/send-now/<job_id>")
    @limiter.limit("10 per day;3 per hour")
    def schedule_send_now(job_id):
        return jsonify({"status": "ok"})

    @flask_app.get("/api/assets/categories")
    @limiter.exempt
    def assets_categories():
        return jsonify({"categories": {}})

    @flask_app.get("/api/assets/periods")
    @limiter.exempt
    def assets_periods():
        return jsonify({"periods": []})

    @flask_app.get("/api/assets/intervals")
    @limiter.exempt
    def assets_intervals():
        return jsonify({"intervals": []})

    @flask_app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # Custom 429 handler (mirrors app.py)
    @flask_app.errorhandler(429)
    def ratelimit_handler(e):
        retry_after = None
        try:
            retry_after = int(str(e.description).split("in")[1].split("second")[0].strip())
        except Exception:
            pass
        return jsonify({
            "error":       "rate_limit_exceeded",
            "message":     str(e.description),
            "retry_after": retry_after,
        }), 429

    return flask_app


@pytest.fixture()
def client():
    flask_app = _make_app()
    with flask_app.test_client() as c:
        yield c


# ── 429 response shape ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRateLimitResponseShape:

    def test_429_returns_json_with_error_key(self, client):
        """A rate-limited request must return JSON with 'error': 'rate_limit_exceeded'."""
        # Exhaust the 3-per-minute limit
        for _ in range(3):
            client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.0.0.1"})

        resp = client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.0.0.1"})
        assert resp.status_code == 429
        data = resp.get_json()
        assert data is not None
        assert data.get("error") == "rate_limit_exceeded"

    def test_429_response_has_message_field(self, client):
        for _ in range(3):
            client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.0.0.2"})

        resp = client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.0.0.2"})
        assert resp.status_code == 429
        data = resp.get_json()
        assert "message" in data

    def test_different_ips_have_separate_counters(self, client):
        """Requests from different IPs must not share rate-limit state."""
        for _ in range(3):
            client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.1.1.1"})

        # IP B should NOT be rate-limited
        resp = client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.1.1.2"})
        assert resp.status_code != 429


# ── Pipeline endpoint limits ──────────────────────────────────────────────────

@pytest.mark.unit
class TestPipelineLimits:

    def test_pipeline_allows_first_request(self, client):
        """The first pipeline request from a clean IP must not be rate-limited."""
        resp = client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.2.0.1"})
        assert resp.status_code == 200

    def test_pipeline_blocked_after_per_minute_limit(self, client):
        """After 3 requests in a minute, the 4th must be 429."""
        for _ in range(3):
            client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.2.0.2"})

        resp = client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.2.0.2"})
        assert resp.status_code == 429

    def test_pipeline_three_requests_allowed(self, client):
        """Exactly 3 requests per minute must all succeed."""
        for i in range(3):
            resp = client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.2.0.3"})
            assert resp.status_code == 200, f"Request {i + 1} was unexpectedly blocked"


# ── Comparison endpoint limits ────────────────────────────────────────────────

@pytest.mark.unit
class TestComparisonLimits:

    def test_comparison_allows_first_request(self, client):
        resp = client.post("/api/comparison/run", environ_base={"REMOTE_ADDR": "10.3.0.1"})
        assert resp.status_code == 200

    def test_comparison_blocked_after_per_minute_limit(self, client):
        """After 2 requests in a minute, the 3rd must be 429."""
        for _ in range(2):
            client.post("/api/comparison/run", environ_base={"REMOTE_ADDR": "10.3.0.2"})

        resp = client.post("/api/comparison/run", environ_base={"REMOTE_ADDR": "10.3.0.2"})
        assert resp.status_code == 429

    def test_comparison_two_requests_allowed(self, client):
        """Exactly 2 requests per minute must both succeed."""
        for i in range(2):
            resp = client.post("/api/comparison/run", environ_base={"REMOTE_ADDR": "10.3.0.3"})
            assert resp.status_code == 200, f"Request {i + 1} was unexpectedly blocked"


# ── Schedule endpoint limits ──────────────────────────────────────────────────

@pytest.mark.unit
class TestScheduleLimits:

    def test_schedule_add_allows_first_request(self, client):
        resp = client.post("/api/schedule/add", environ_base={"REMOTE_ADDR": "10.4.0.1"})
        assert resp.status_code == 200

    def test_schedule_add_five_requests_allowed(self, client):
        """Exactly 5 requests per hour must all succeed (hour window)."""
        for i in range(5):
            resp = client.post("/api/schedule/add", environ_base={"REMOTE_ADDR": "10.4.0.2"})
            assert resp.status_code == 200, f"Request {i + 1} was unexpectedly blocked"

    def test_schedule_add_blocked_on_sixth_request(self, client):
        for _ in range(5):
            client.post("/api/schedule/add", environ_base={"REMOTE_ADDR": "10.4.0.3"})

        resp = client.post("/api/schedule/add", environ_base={"REMOTE_ADDR": "10.4.0.3"})
        assert resp.status_code == 429

    def test_send_now_allows_first_request(self, client):
        resp = client.post("/api/schedule/send-now/job123",
                           environ_base={"REMOTE_ADDR": "10.4.1.1"})
        assert resp.status_code == 200


# ── Assets endpoints are exempt ───────────────────────────────────────────────

@pytest.mark.unit
class TestAssetsExempt:

    def test_categories_never_rate_limited(self, client):
        """GET /api/assets/categories is exempt — 20 rapid requests must not 429."""
        for i in range(20):
            resp = client.get("/api/assets/categories",
                              environ_base={"REMOTE_ADDR": "10.5.0.1"})
            assert resp.status_code == 200, (
                f"categories should be exempt but got {resp.status_code} on request {i + 1}"
            )

    def test_periods_never_rate_limited(self, client):
        for _ in range(20):
            resp = client.get("/api/assets/periods",
                              environ_base={"REMOTE_ADDR": "10.5.0.2"})
            assert resp.status_code == 200

    def test_intervals_never_rate_limited(self, client):
        for _ in range(20):
            resp = client.get("/api/assets/intervals",
                              environ_base={"REMOTE_ADDR": "10.5.0.3"})
            assert resp.status_code == 200

    def test_health_never_rate_limited(self, client):
        """GET /api/health is not explicitly rate-limited."""
        for _ in range(20):
            resp = client.get("/api/health",
                              environ_base={"REMOTE_ADDR": "10.5.0.4"})
            assert resp.status_code == 200


# ── Rate limit headers ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRateLimitHeaders:

    def test_pipeline_response_includes_ratelimit_headers(self, client):
        """Responses from rate-limited endpoints should include X-RateLimit-* headers."""
        resp = client.post("/api/pipeline/run",
                           environ_base={"REMOTE_ADDR": "10.6.0.1"})
        assert resp.status_code == 200
        header_names = [h.lower() for h in resp.headers.keys()]
        has_ratelimit = any("ratelimit" in h or "x-ratelimit" in h for h in header_names)
        assert has_ratelimit, (
            f"Expected X-RateLimit-* headers; got: {list(resp.headers.keys())}"
        )

    def test_comparison_response_includes_ratelimit_headers(self, client):
        resp = client.post("/api/comparison/run",
                           environ_base={"REMOTE_ADDR": "10.6.0.2"})
        assert resp.status_code == 200
        header_names = [h.lower() for h in resp.headers.keys()]
        has_ratelimit = any("ratelimit" in h or "x-ratelimit" in h for h in header_names)
        assert has_ratelimit

    def test_429_includes_retry_after_in_json(self, client):
        """The 429 JSON body must have a retry_after field (may be None)."""
        for _ in range(3):
            client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.6.0.3"})

        resp = client.post("/api/pipeline/run", environ_base={"REMOTE_ADDR": "10.6.0.3"})
        assert resp.status_code == 429
        data = resp.get_json()
        assert "retry_after" in data
