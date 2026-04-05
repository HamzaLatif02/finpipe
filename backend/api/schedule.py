import logging
import os
import re
import secrets
import sys
import threading


from flask import Blueprint, jsonify, request

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scheduler import add_job, remove_job, list_jobs, get_stored_token, get_job_meta, run_pipeline_and_email  # noqa: E402  # noqa: E402

schedule_bp = Blueprint("schedule", __name__)
logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_REQUIRED_CONFIG = {"symbol", "name", "asset_type", "currency", "period", "interval"}
_VALID_FREQUENCIES = {"daily", "weekly", "monthly"}


def _validate_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match(addr or ""))


def _parse_token_header() -> set:
    """Parse X-Schedule-Token header into a set of token strings."""
    raw = request.headers.get("X-Schedule-Token", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


@schedule_bp.post("/add")
def add():
    body = request.get_json(silent=True) or {}

    email     = (body.get("email") or "").strip()
    frequency = (body.get("frequency") or "").strip()
    config    = body.get("config") or {}

    # ── Validate
    errors = []
    if not _validate_email(email):
        errors.append("Valid email address is required.")
    if frequency not in _VALID_FREQUENCIES:
        errors.append(f"frequency must be one of: {', '.join(_VALID_FREQUENCIES)}.")
    missing_cfg = _REQUIRED_CONFIG - config.keys()
    if missing_cfg:
        errors.append(f"config is missing fields: {', '.join(sorted(missing_cfg))}.")
    if frequency == "weekly" and not body.get("day_of_week"):
        errors.append("day_of_week is required for weekly frequency.")
    if frequency == "monthly" and not body.get("day"):
        errors.append("day is required for monthly frequency.")
    if errors:
        return jsonify({"error": " ".join(errors)}), 400

    schedule = {
        "frequency":   frequency,
        "hour":        int(body.get("hour", 8)),
        "minute":      int(body.get("minute", 0)),
        "day_of_week": body.get("day_of_week"),
        "day":         body.get("day"),
    }

    safe_email = re.sub(r"[^a-zA-Z0-9]", "_", email)
    job_id     = f"{config['symbol']}_{safe_email}_{frequency}"

    token = secrets.token_urlsafe(32)

    try:
        add_job(job_id, config, schedule, email, token)
    except Exception as exc:
        logger.exception("add_job failed")
        return jsonify({"error": str(exc)}), 500

    # Retrieve next_run_time from the live job list
    jobs     = list_jobs()
    job      = next((j for j in jobs if j["job_id"] == job_id), None)
    next_run = job["next_run_time"] if job else None

    return jsonify({"status": "scheduled", "job_id": job_id, "token": token, "next_run": next_run})


@schedule_bp.delete("/remove/<job_id>")
def remove(job_id: str):
    client_tokens = _parse_token_header()

    stored_token = get_stored_token(job_id)
    if stored_token is None:
        return jsonify({"error": f"Job '{job_id}' not found."}), 404
    if stored_token not in client_tokens:
        return jsonify({"error": "invalid token"}), 403

    try:
        existed = remove_job(job_id)
    except Exception as exc:
        logger.exception("remove_job failed")
        return jsonify({"error": str(exc)}), 500

    if not existed:
        return jsonify({"error": f"Job '{job_id}' not found."}), 404

    return jsonify({"status": "removed", "job_id": job_id})


@schedule_bp.post("/send-now/<job_id>")
def send_now(job_id: str):
    """Validate the token synchronously, then run the pipeline + email in a
    background thread and return immediately.

    Running SMTP inside a gunicorn sync worker blocks the worker thread for
    the entire SMTP round-trip (up to 5 × socket_timeout seconds).  If the
    outbound connection to smtp.gmail.com is rate-limited or slow, gunicorn's
    SIGABRT fires and raises SystemExit(1) — which bypasses all our
    except-Exception handlers.  Moving the work off the request thread fixes
    the timeout entirely.
    """
    client_tokens = _parse_token_header()

    stored_token = get_stored_token(job_id)
    if stored_token is None:
        return jsonify({"error": f"Job '{job_id}' not found."}), 404
    if stored_token not in client_tokens:
        return jsonify({"error": "Invalid token — cannot send this report."}), 403

    meta   = get_job_meta(job_id)
    config = meta["config"]
    email  = meta["email"]
    symbol = config["symbol"]

    logger.info("SEND NOW queued for %s -> %s", symbol, email)

    def _bg():
        try:
            run_pipeline_and_email(config, email)
            logger.info("SEND NOW completed for %s -> %s", symbol, email)
        except Exception:
            logger.exception("SEND NOW background task failed for %s", symbol)

    thread = threading.Thread(target=_bg, daemon=True, name=f"sendnow-{job_id}")
    thread.start()

    return jsonify({
        "status":  "queued",
        "symbol":  symbol,
        "email":   email,
        "message": f"Report is being generated. Email will arrive at {email} in ~1–2 minutes.",
    })


@schedule_bp.get("/list")
def list_all():
    client_tokens = _parse_token_header()
    if not client_tokens:
        return jsonify({"jobs": []})

    try:
        all_jobs = list_jobs()
    except Exception as exc:
        logger.exception("list_jobs failed")
        return jsonify({"error": str(exc)}), 500

    filtered = [
        {
            "job_id":        j["job_id"],
            "symbol":        j["symbol"],
            "name":          j["name"],
            "email":         j["email"],
            "frequency":     j["frequency"],
            "next_run_time": j["next_run_time"],
        }
        for j in all_jobs
        if get_stored_token(j["job_id"]) in client_tokens
    ]

    return jsonify({"jobs": filtered})
