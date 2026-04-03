"""
Background scheduler for automated pipeline + email jobs.
Jobs are persisted to data/scheduled_jobs.json so they survive restarts.
"""
import json
import logging
import os
import secrets
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Project root is one level above backend/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import DATA_DIR  # noqa: E402 — needs _ROOT on sys.path first

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_jobs_meta: dict = {}  # job_id → {config, email, schedule}
_JOBS_FILE = os.path.join(DATA_DIR, "scheduled_jobs.json")


# ── Persistence ───────────────────────────────────────────────────────────────

def _save_jobs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_JOBS_FILE, "w") as f:
        json.dump(_jobs_meta, f, indent=2, default=str)


def _load_jobs() -> dict:
    if not os.path.isfile(_JOBS_FILE):
        return {}
    with open(_JOBS_FILE) as f:
        return json.load(f)


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email(to_address: str, subject: str, body: str, attachment_path: str = None) -> None:
    host     = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port     = int(os.getenv("SMTP_PORT", 587))
    user     = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")

    msg = MIMEMultipart()
    msg["From"]    = user
    msg["To"]      = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_path and Path(attachment_path).is_file():
        with open(attachment_path, "rb") as fh:
            part = MIMEApplication(fh.read(), _subtype="pdf")
            part["Content-Disposition"] = (
                f'attachment; filename="{Path(attachment_path).name}"'
            )
            msg.attach(part)

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.send_message(msg)

    logger.info("Email sent to %s — %s", to_address, subject)


# ── Job function (runs in background thread) ──────────────────────────────────

def _execute_job(config: dict, email: str) -> None:
    symbol = config["symbol"]
    logger.info("Scheduled job starting: %s → %s", symbol, email)
    try:
        from fetcher import fetch_data
        from cleaner import clean_data
        from db import init_db, insert_prices, insert_info
        from analysis import run_analysis
        from charts import generate_charts
        from report import generate_report

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

        logger.info("Scheduled job completed: %s", symbol)
    except Exception:
        logger.exception("Scheduled job failed for %s", symbol)


# ── Trigger builder ───────────────────────────────────────────────────────────

def _build_trigger(schedule: dict) -> CronTrigger:
    frequency  = schedule["frequency"]
    hour       = int(schedule.get("hour", 8))
    minute     = int(schedule.get("minute", 0))
    if frequency == "weekly":
        return CronTrigger(day_of_week=schedule["day_of_week"], hour=hour, minute=minute)
    if frequency == "monthly":
        return CronTrigger(day=int(schedule["day"]), hour=hour, minute=minute)
    return CronTrigger(hour=hour, minute=minute)  # daily


# ── Public API ────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    global _scheduler, _jobs_meta
    if _scheduler and _scheduler.running:
        return
    _scheduler = BackgroundScheduler()
    _jobs_meta = _load_jobs()
    # Back-fill tokens for jobs created before token auth was added
    needs_save = False
    for meta in _jobs_meta.values():
        if "token" not in meta:
            meta["token"] = secrets.token_urlsafe(32)
            needs_save = True
    if needs_save:
        _save_jobs()
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
            logger.info("Restored scheduled job: %s", job_id)
        except Exception:
            logger.exception("Failed to restore job %s", job_id)
    _scheduler.start()
    logger.info("Scheduler started (%d job(s) loaded)", len(_jobs_meta))


def add_job(job_id: str, config: dict, schedule: dict, email: str, token: str) -> None:
    if not _scheduler:
        raise RuntimeError("Scheduler is not running.")
    trigger = _build_trigger(schedule)
    _scheduler.add_job(
        _execute_job,
        trigger=trigger,
        args=[config, email],
        id=job_id,
        replace_existing=True,
        name=f"{config['symbol']} — {schedule['frequency']}",
    )
    _jobs_meta[job_id] = {"config": config, "email": email, "schedule": schedule, "token": token}
    _save_jobs()
    logger.info("Job added: %s", job_id)


def get_stored_token(job_id: str):
    """Return the stored token for a job, or None if the job doesn't exist."""
    meta = _jobs_meta.get(job_id)
    return meta["token"] if meta else None


def remove_job(job_id: str) -> bool:
    if not _scheduler:
        return False
    try:
        _scheduler.remove_job(job_id)
    except Exception:
        pass  # job may not exist in scheduler if it was never loaded
    existed = job_id in _jobs_meta
    _jobs_meta.pop(job_id, None)
    _save_jobs()
    logger.info("Job removed: %s", job_id)
    return existed


def list_jobs() -> list:
    if not _scheduler:
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
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")
