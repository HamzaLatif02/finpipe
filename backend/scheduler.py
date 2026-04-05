"""
Background scheduler for automated pipeline + email jobs.
Jobs are persisted to PostgreSQL (DATABASE_URL) so they survive Render
service restarts and redeploys.
"""
import base64
import logging
import os
import sys
import urllib.request
from pathlib import Path

# Do NOT capture PID at module level — that freezes the master's PID.
# Call os.getpid() inline so each log line reflects the actual running process.
def _pid() -> int:
    return os.getpid()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pytz import timezone

_TZ = timezone("Europe/London")

# Single module-level scheduler instance — never reassigned.
# All functions (add_job, _heartbeat, etc.) reference this same object.
_scheduler = BackgroundScheduler(timezone=_TZ)

# Project root is one level above backend/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pg_jobs import init_pg_jobs_table, pg_save_job, pg_load_jobs, pg_delete_job  # noqa: E402

logger = logging.getLogger(__name__)

# job_id → {config, email, schedule, token}
# In-memory cache of the SQLite scheduled_jobs table.
# Token is a secret credential — never log it.
_jobs_meta: dict = {}


# ── Email (Resend API — HTTPS, works on Render free tier) ─────────────────────

def _send_email(to_address: str, subject: str, body: str, attachment_path: str = None) -> None:
    """Send an email via the Resend API.

    Uses HTTPS rather than SMTP so it works on Render's free tier,
    which blocks outbound connections on port 587.
    Requires RESEND_API_KEY in the environment.
    """
    import resend  # imported here so the module loads without it if not installed

    resend.api_key = os.getenv("RESEND_API_KEY", "")
    if not resend.api_key:
        raise RuntimeError("RESEND_API_KEY is not set in the environment.")

    params: resend.Emails.SendParams = {
        "from":    "Financial Pipeline <reports@finpipe.xyz>",
        "to":      [to_address],
        "subject": subject,
        "text":    body,
    }

    if attachment_path and Path(attachment_path).is_file():
        with open(attachment_path, "rb") as fh:
            pdf_b64 = base64.b64encode(fh.read()).decode("utf-8")
        params["attachments"] = [
            {
                "filename": Path(attachment_path).name,
                "content":  pdf_b64,
            }
        ]

    response = resend.Emails.send(params)
    logger.info("Email sent via Resend to %s — id: %s", to_address, response["id"])


# ── Core pipeline + email logic (raises on any failure) ───────────────────────

def run_pipeline_and_email(config: dict, email: str) -> None:
    """Run the full pipeline for *config* and email the PDF to *email*.

    Raises on any failure so callers can decide whether to swallow or
    surface the exception (scheduled jobs swallow; send-now surfaces it).
    """
    from fetcher import fetch_data
    from cleaner import clean_data
    from db import init_db, insert_prices, insert_info
    from analysis import run_analysis
    from charts import generate_charts
    from report import generate_report

    symbol = config["symbol"]
    init_db()
    fetched     = fetch_data(config)
    cleaned_df  = clean_data(config)
    insert_prices(config, cleaned_df)
    insert_info(config, fetched["info"])
    analysis    = run_analysis(config)
    chart_paths = generate_charts(config, analysis)
    pdf_path    = generate_report(config, analysis, chart_paths)

    subject = f"Financial Report: {config['name']} ({symbol})"
    body = (
        f"Please find attached the automated financial report for "
        f"{config['name']} ({symbol}).\n\n"
        f"Period: {config.get('period', '')}  |  "
        f"Interval: {config.get('interval', '')}\n\n"
        "This report was generated automatically by Financial Pipeline.\n"
        "Not financial advice."
    )

    recipients = [email]
    default_recipient = os.getenv("REPORT_RECIPIENT", "")
    if default_recipient and default_recipient not in recipients:
        recipients.append(default_recipient)

    for addr in recipients:
        _send_email(addr, subject, body, pdf_path)

    logger.info("Pipeline and email completed for %s", symbol)


# ── Job function (runs in background thread via APScheduler) ──────────────────

def _execute_job(config: dict, email: str) -> None:
    """APScheduler entry point.  Swallows all exceptions so a failing job
    does not crash the scheduler thread."""
    symbol = config["symbol"]
    logger.info("Scheduled job starting: %s -> %s", symbol, email)
    try:
        run_pipeline_and_email(config, email)
        logger.info("Scheduled job completed: %s", symbol)
    except Exception:
        logger.exception("Scheduled job failed for %s", symbol)


# ── Keepalive (prevents Render free-tier from sleeping) ───────────────────────

def _keepalive() -> None:
    """Ping the app's own health endpoint every 14 min to keep Render awake.

    Render's free-tier shuts down processes after 15 min of inactivity.
    APScheduler dies with the process, so any scheduled jobs would be missed.
    This job only activates when RENDER_EXTERNAL_URL is present in the
    environment (automatically set by Render) — it is a no-op locally.
    """
    url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not url:
        return
    target = f"{url}/api/health"
    try:
        with urllib.request.urlopen(target, timeout=10) as resp:
            logger.info("Keepalive ping → %s  [%s]", target, resp.status)
    except Exception as exc:
        logger.warning("Keepalive ping failed: %s", exc)


def _heartbeat() -> None:
    """Log a heartbeat every 5 minutes to confirm the scheduler thread is alive."""
    # Refresh the in-memory job store before counting, so any jobs added
    # since the last heartbeat are included in the count.
    try:
        _scheduler._jobstores["default"].get_all_jobs()
    except Exception:
        pass
    all_jobs = _scheduler.get_jobs()
    logger.info("[PID %d] ALL JOBS IN SCHEDULER: %s", _pid(), [j.id for j in all_jobs])
    user_jobs = [j for j in all_jobs if not j.id.startswith("__")]
    ids = [j.id for j in user_jobs] or ["none"]
    logger.info(
        "[PID %d] SCHEDULER HEARTBEAT — %d user job(s): %s",
        _pid(), len(user_jobs), ", ".join(ids),
    )


# ── Trigger builder ───────────────────────────────────────────────────────────

def _build_trigger(schedule: dict) -> CronTrigger:
    """Build a Europe/London-pinned CronTrigger.

    Hour/minute values are stored as London local time (the frontend sends
    exactly what the user typed).  Passing timezone=_TZ means APScheduler
    fires the job at that wall-clock time in London, automatically handling
    the GMT→BST and BST→GMT transitions without any manual offset arithmetic.
    """
    frequency = schedule["frequency"]
    hour      = int(schedule.get("hour", 8))
    minute    = int(schedule.get("minute", 0))
    if frequency == "weekly":
        return CronTrigger(day_of_week=schedule["day_of_week"], hour=hour, minute=minute, timezone=_TZ)
    if frequency == "monthly":
        return CronTrigger(day=int(schedule["day"]), hour=hour, minute=minute, timezone=_TZ)
    return CronTrigger(hour=hour, minute=minute, timezone=_TZ)  # daily


# ── Public API ────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    global _jobs_meta
    if _scheduler.running:
        return

    # ── Load persisted jobs from SQLite ───────────────────────────────────────
    logger.info("=" * 60)
    logger.info("[PID %d] SCHEDULER STARTING  (timezone: %s)", _pid(), _TZ)

    init_pg_jobs_table()
    rows = pg_load_jobs()
    _jobs_meta = {r["job_id"]: {"config": r["config"], "email": r["email"], "schedule": r["schedule"], "token": r["token"]} for r in rows}
    logger.info("[PID %d] Jobs loaded from PostgreSQL: %d", _pid(), len(_jobs_meta))

    if not _jobs_meta:
        logger.info("[PID %d] SCHEDULER: no user jobs in DB — schedule via the web app.", _pid())

    # ── Register user-defined jobs ─────────────────────────────────────────────
    for job_id, meta in _jobs_meta.items():
        try:
            trigger = _build_trigger(meta["schedule"])
            _scheduler.add_job(
                _execute_job,
                trigger=trigger,
                args=[meta["config"], meta["email"]],
                id=job_id,
                replace_existing=True,
                name=f"{meta['config']['symbol']} — {meta['schedule']['frequency']}",
            )
            logger.info("[PID %d] Restored job: %s", _pid(), job_id)
        except Exception as exc:
            logger.error("[PID %d] Failed to restore job %s: %s", _pid(), job_id, exc)

    # ── Infrastructure jobs ────────────────────────────────────────────────────
    # Keepalive: pings /api/health every 14 min to prevent Render free-tier
    # spin-down.  IntervalTrigger is more reliable than CronTrigger here
    # because it fires relative to when the scheduler started, not at fixed
    # clock minutes (which could all fall inside a spin-down window).
    _scheduler.add_job(
        _keepalive,
        IntervalTrigger(minutes=14, timezone=_TZ),
        id="__keepalive__",
        replace_existing=True,
        name="Render keepalive",
    )
    # Heartbeat: logs a message every 5 min so Render logs confirm the
    # scheduler thread is still alive.
    _scheduler.add_job(
        _heartbeat,
        IntervalTrigger(minutes=5, timezone=_TZ),
        id="__heartbeat__",
        replace_existing=True,
        name="Scheduler heartbeat",
    )

    _scheduler.start()

    # ── Startup summary ────────────────────────────────────────────────────────
    user_jobs = [j for j in _scheduler.get_jobs() if not j.id.startswith("__")]
    logger.info("[PID %d] SCHEDULER STARTED — registered %d user job(s) from DB with APScheduler", _pid(), len(user_jobs))
    for j in user_jobs:
        logger.info("[PID %d] REGISTERED: %s | next run: %s", _pid(), j.id, j.next_run_time)
    if not user_jobs:
        logger.info("[PID %d]   (no user jobs — reschedule via the web app)", _pid())
    logger.info("[PID %d] SCHEDULER started successfully", _pid())
    logger.info("=" * 60)


def add_job(job_id: str, config: dict, schedule: dict, email: str, token: str) -> None:
    if not _scheduler.running:
        logger.warning("[PID %d] Scheduler not running — attempting recovery start", _pid())
        start_scheduler()
    if not _scheduler.running:
        raise RuntimeError("Scheduler failed to start — cannot add job")
    trigger = _build_trigger(schedule)
    _scheduler.add_job(
        _execute_job,
        trigger=trigger,
        args=[config, email],
        id=job_id,
        replace_existing=True,
        name=f"{config['symbol']} — {schedule['frequency']}",
    )
    # Force the in-memory job store to refresh, then confirm the job is live.
    try:
        _scheduler._jobstores["default"].get_all_jobs()
    except Exception:
        pass
    live_job = _scheduler.get_job(job_id)
    if live_job:
        logger.info(
            "[PID %d] ADD JOB confirmed in live scheduler: %s | next run: %s",
            _pid(), job_id, live_job.next_run_time,
        )
    else:
        logger.error(
            "[PID %d] ADD JOB failed to appear in live scheduler: %s",
            _pid(), job_id,
        )
    _jobs_meta[job_id] = {"config": config, "email": email, "schedule": schedule, "token": token}
    pg_save_job(job_id, config, schedule, email, token)


def get_stored_token(job_id: str):
    """Return the stored token for a job, or None if the job doesn't exist."""
    meta = _jobs_meta.get(job_id)
    return meta["token"] if meta else None


def get_job_meta(job_id: str):
    """Return the full meta dict for a job, or None if it doesn't exist."""
    return _jobs_meta.get(job_id)


def remove_job(job_id: str) -> bool:
    if not _scheduler.running:
        return False
    try:
        _scheduler.remove_job(job_id)
    except Exception:
        pass  # job may not exist in scheduler if it was never loaded
    existed = job_id in _jobs_meta
    _jobs_meta.pop(job_id, None)
    pg_delete_job(job_id)
    logger.info("Job removed: %s", job_id)
    return existed


def list_jobs() -> list:
    if not _scheduler.running:
        return []
    result = []
    apscheduler_jobs = {j.id: j for j in _scheduler.get_jobs()}
    for job_id, meta in _jobs_meta.items():
        apj = apscheduler_jobs.get(job_id)
        result.append({
            "job_id":        job_id,
            "symbol":        meta["config"]["symbol"],
            "name":          meta["config"]["name"],
            "email":         meta["email"],
            "frequency":     meta["schedule"]["frequency"],
            "next_run_time": str(apj.next_run_time) if apj and apj.next_run_time else None,
        })
    return result


def shutdown_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")
