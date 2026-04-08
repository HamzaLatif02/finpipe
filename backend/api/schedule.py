import logging
import os
import re
import secrets
import sys
import threading

from flask import jsonify, request
from flask_smorest import Blueprint

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scheduler import (  # noqa: E402
    add_job, activate_job, remove_job, list_jobs,
    get_stored_token, get_job_meta, run_pipeline_and_email,
)
from pg_jobs import confirm_job, pg_load_pending_jobs  # noqa: E402
from extensions import limiter  # noqa: E402
from schemas import (          # noqa: E402
    ScheduleAddResponseSchema, ConfirmResponseSchema, RemoveJobResponseSchema,
    SendNowResponseSchema, ScheduleListResponseSchema, PendingListResponseSchema,
    ErrorResponseSchema,
)

schedule_bp = Blueprint(
    "schedule", __name__,
    description="Schedule recurring email reports with double opt-in confirmation.",
)
logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_REQUIRED_CONFIG   = {"symbol", "name", "asset_type", "currency", "period", "interval"}
_VALID_FREQUENCIES = {"daily", "weekly", "monthly"}


def _validate_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match(addr or ""))


def _parse_token_header() -> set:
    """Parse X-Schedule-Token header into a set of token strings."""
    raw = request.headers.get("X-Schedule-Token", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _send_confirmation_email(email: str, symbol: str, schedule: dict, confirm_url: str) -> None:
    """Send a double opt-in confirmation email via Resend."""
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY", "")
    if not resend.api_key:
        raise RuntimeError("RESEND_API_KEY is not set.")

    frequency = schedule["frequency"]
    hour      = schedule["hour"]
    minute    = str(schedule["minute"]).zfill(2)

    resend.Emails.send({
        "from":    "Financial Pipeline <reports@finpipe.xyz>",
        "to":      [email],
        "subject": f"Confirm your scheduled {symbol} report",
        "text": (
            f"You requested a {frequency} {symbol} report at {hour}:{minute} (London time).\n\n"
            f"Click the link below to confirm and activate your scheduled report:\n\n"
            f"{confirm_url}\n\n"
            f"This link expires in 24 hours.\n\n"
            f"If you did not request this, ignore this email — no report will be scheduled."
        ),
    })
    logger.info("Confirmation email sent to %s for %s", email, symbol)


# ── POST /add ──────────────────────────────────────────────────────────────────

@schedule_bp.post("/add")
@schedule_bp.response(200, ScheduleAddResponseSchema())
@schedule_bp.alt_response(400, schema=ErrorResponseSchema())
@schedule_bp.alt_response(429, schema=ErrorResponseSchema(), description="Rate limit exceeded")
@schedule_bp.alt_response(500, schema=ErrorResponseSchema())
@schedule_bp.doc(
    summary="Schedule a recurring report",
    description=(
        "Creates a pending scheduled job and sends a double opt-in confirmation email. "
        "The job is not activated until the user clicks the confirmation link. "
        "**Rate limit:** 5/hr · 20/day."
    ),
    requestBody={
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["email", "frequency", "config"],
                    "properties": {
                        "email":       {"type": "string", "example": "user@example.com"},
                        "frequency":   {"type": "string", "enum": ["daily", "weekly", "monthly"]},
                        "hour":        {"type": "integer", "example": 8},
                        "minute":      {"type": "integer", "example": 0},
                        "day_of_week": {"type": "string",  "example": "mon",
                                        "description": "Required for weekly frequency."},
                        "day":         {"type": "integer", "example": 1,
                                        "description": "Day of month. Required for monthly frequency."},
                        "config": {
                            "type": "object",
                            "required": ["symbol", "name", "asset_type", "currency", "period", "interval"],
                            "properties": {
                                "symbol":     {"type": "string", "example": "AAPL"},
                                "name":       {"type": "string", "example": "Apple Inc."},
                                "asset_type": {"type": "string", "example": "Stocks"},
                                "currency":   {"type": "string", "example": "USD"},
                                "period":     {"type": "string", "example": "1y"},
                                "interval":   {"type": "string", "example": "1d"},
                            },
                        },
                    },
                }
            }
        },
    },
)
@limiter.limit("20 per day;5 per hour")
def add():
    body = request.get_json(silent=True) or {}

    email     = (body.get("email") or "").strip()
    frequency = (body.get("frequency") or "").strip()
    config    = body.get("config") or {}

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

    safe_email    = re.sub(r"[^a-zA-Z0-9]", "_", email)
    job_id        = f"{config['symbol']}_{safe_email}_{frequency}"
    token         = secrets.token_urlsafe(32)
    confirm_token = secrets.token_urlsafe(32)

    try:
        add_job(job_id, config, schedule, email, token, confirm_token)
    except Exception as exc:
        logger.exception("add_job failed")
        return jsonify({"error": str(exc)}), 500

    # Build confirmation URL and send email
    base_url    = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5001").rstrip("/")
    confirm_url = f"{base_url}/confirm?ct={confirm_token}"

    try:
        _send_confirmation_email(email, config["symbol"], schedule, confirm_url)
    except Exception as exc:
        logger.exception("Failed to send confirmation email")
        return jsonify({"error": f"Job saved but confirmation email failed: {exc}"}), 500

    return jsonify({
        "status":  "pending",
        "job_id":  job_id,
        "token":   token,
        "email":   email,
        "message": "Check your inbox to confirm this scheduled report.",
    })


# ── GET /confirm ───────────────────────────────────────────────────────────────

@schedule_bp.get("/confirm")
@schedule_bp.response(200, ConfirmResponseSchema())
@schedule_bp.alt_response(400, schema=ErrorResponseSchema())
@schedule_bp.alt_response(500, schema=ErrorResponseSchema())
def confirm():
    """Activate a pending scheduled job via its confirmation token.

    Query parameter: `ct` — the confirmation token from the email link.
    """
    ct = request.args.get("ct", "").strip()
    if not ct:
        return jsonify({"error": "Missing confirmation token."}), 400

    job = confirm_job(ct)
    if not job:
        return jsonify({
            "status":  "invalid",
            "message": "This confirmation link is invalid or has already been used.",
        }), 400

    try:
        next_run = activate_job(job["job_id"])
    except Exception as exc:
        logger.exception("activate_job failed for %s", job["job_id"])
        return jsonify({"error": str(exc)}), 500

    logger.info("Job confirmed and activated: %s for %s", job["job_id"], job["email"])

    return jsonify({
        "status":    "confirmed",
        "symbol":    job["config"]["symbol"],
        "job_id":    job["job_id"],
        "token":     job["token"],
        "next_run":  next_run,
        "message":   "Your scheduled report has been activated.",
    })


# ── DELETE /remove/<job_id> ────────────────────────────────────────────────────

@schedule_bp.delete("/remove/<job_id>")
@schedule_bp.response(200, RemoveJobResponseSchema())
@schedule_bp.alt_response(403, schema=ErrorResponseSchema())
@schedule_bp.alt_response(404, schema=ErrorResponseSchema())
@schedule_bp.alt_response(500, schema=ErrorResponseSchema())
def remove(job_id: str):
    """Cancel and remove a scheduled job.

    Requires the `X-Schedule-Token` header containing the token returned when the job was created.
    """
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


# ── POST /send-now/<job_id> ────────────────────────────────────────────────────

@schedule_bp.post("/send-now/<job_id>")
@schedule_bp.response(200, SendNowResponseSchema())
@schedule_bp.alt_response(400, schema=ErrorResponseSchema())
@schedule_bp.alt_response(403, schema=ErrorResponseSchema())
@schedule_bp.alt_response(404, schema=ErrorResponseSchema())
@schedule_bp.alt_response(429, schema=ErrorResponseSchema(), description="Rate limit exceeded")
@schedule_bp.doc(
    summary="Trigger an immediate report send",
    description=(
        "Generates and emails the report for the given job right now, "
        "outside of the regular schedule. "
        "Requires the `X-Schedule-Token` header. "
        "**Rate limit:** 3/hr · 10/day."
    ),
)
@limiter.limit("10 per day;3 per hour")
def send_now(job_id: str):
    client_tokens = _parse_token_header()

    stored_token = get_stored_token(job_id)
    if stored_token is None:
        return jsonify({"error": f"Job '{job_id}' not found."}), 404
    if stored_token not in client_tokens:
        return jsonify({"error": "Invalid token — cannot send this report."}), 403

    meta   = get_job_meta(job_id)
    if not meta.get("confirmed", True):   # pending jobs cannot be sent now
        return jsonify({"error": "This job has not been confirmed yet. Check your inbox."}), 400

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


# ── GET /list ──────────────────────────────────────────────────────────────────

@schedule_bp.get("/list")
@schedule_bp.response(200, ScheduleListResponseSchema())
@schedule_bp.alt_response(500, schema=ErrorResponseSchema())
def list_all():
    """List all confirmed scheduled jobs owned by the caller.

    Pass one or more job tokens in `X-Schedule-Token` (comma-separated).
    Only jobs whose token matches are returned.
    """
    client_tokens = _parse_token_header()
    if not client_tokens:
        return jsonify({"jobs": []})

    try:
        all_jobs = list_jobs()   # confirmed only, from APScheduler + _jobs_meta
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


# ── GET /pending ───────────────────────────────────────────────────────────────

@schedule_bp.get("/pending")
@schedule_bp.response(200, PendingListResponseSchema())
@schedule_bp.alt_response(500, schema=ErrorResponseSchema())
def list_pending():
    """List pending (unconfirmed) scheduled jobs owned by the caller.

    Pass one or more job tokens in `X-Schedule-Token` (comma-separated).
    """
    client_tokens = _parse_token_header()
    if not client_tokens:
        return jsonify({"jobs": []})

    try:
        pending = pg_load_pending_jobs()
    except Exception as exc:
        logger.exception("pg_load_pending_jobs failed")
        return jsonify({"error": str(exc)}), 500

    filtered = [
        {
            "job_id":    j["job_id"],
            "symbol":    j["config"]["symbol"],
            "name":      j["config"]["name"],
            "email":     j["email"],
            "frequency": j["schedule"]["frequency"],
            "hour":      j["schedule"]["hour"],
            "minute":    j["schedule"]["minute"],
        }
        for j in pending
        if j["token"] in client_tokens
    ]

    return jsonify({"jobs": filtered})


# ── POST /resend-confirmation ──────────────────────────────────────────────────

@schedule_bp.post("/resend-confirmation")
@schedule_bp.response(200, ErrorResponseSchema())
@schedule_bp.alt_response(400, schema=ErrorResponseSchema())
@schedule_bp.alt_response(403, schema=ErrorResponseSchema())
@schedule_bp.alt_response(404, schema=ErrorResponseSchema())
@schedule_bp.alt_response(500, schema=ErrorResponseSchema())
def resend_confirmation():
    """Resend the opt-in confirmation email for a pending job.

    Requires `X-Schedule-Token` header. Body: `{"job_id": "..."}`.
    """
    client_tokens = _parse_token_header()

    body   = request.get_json(silent=True) or {}
    job_id = (body.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"error": "job_id is required."}), 400

    stored_token = get_stored_token(job_id)
    if stored_token is None:
        return jsonify({"error": f"Job '{job_id}' not found."}), 404
    if stored_token not in client_tokens:
        return jsonify({"error": "Invalid token."}), 403

    meta = get_job_meta(job_id)
    if meta.get("confirmed", True):
        return jsonify({"error": "This job is already confirmed."}), 400

    # Generate a fresh confirm_token and update the DB
    from pg_jobs import pg_get_job, pg_save_job
    full_job      = pg_get_job(job_id)
    confirm_token = secrets.token_urlsafe(32)
    pg_save_job(
        job_id,
        full_job["config"],
        full_job["schedule"],
        full_job["email"],
        full_job["token"],
        confirmed=False,
        confirm_token=confirm_token,
    )

    base_url    = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:5001").rstrip("/")
    confirm_url = f"{base_url}/confirm?ct={confirm_token}"

    try:
        _send_confirmation_email(
            full_job["email"],
            full_job["config"]["symbol"],
            full_job["schedule"],
            confirm_url,
        )
    except Exception as exc:
        logger.exception("Failed to resend confirmation email")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"status": "resent", "message": "Confirmation email resent."})
