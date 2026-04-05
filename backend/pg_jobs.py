"""
PostgreSQL-backed persistence for scheduled jobs.

Uses Render's free PostgreSQL database (DATABASE_URL env var) so jobs
survive service restarts and redeploys — unlike SQLite on Render's
ephemeral filesystem which is wiped on every restart.
"""
import json
import logging
import os

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


def _conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to .env for local development "
            "or to Render environment variables for production."
        )
    return psycopg2.connect(url)


def init_pg_jobs_table() -> None:
    """Create the scheduled_jobs table if it does not already exist."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_id        TEXT PRIMARY KEY,
                    symbol        TEXT NOT NULL,
                    name          TEXT NOT NULL,
                    config_json   TEXT NOT NULL,
                    schedule_json TEXT NOT NULL,
                    email         TEXT NOT NULL,
                    token         TEXT NOT NULL,
                    created_at    TIMESTAMP DEFAULT NOW()
                )
            """)
        conn.commit()
    logger.info("PG: scheduled_jobs table ready")


def pg_save_job(job_id: str, config: dict, schedule: dict, email: str, token: str) -> None:
    """Insert or update a scheduled job record."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scheduled_jobs
                    (job_id, symbol, name, config_json, schedule_json, email, token)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    config_json   = EXCLUDED.config_json,
                    schedule_json = EXCLUDED.schedule_json,
                    email         = EXCLUDED.email,
                    token         = EXCLUDED.token
            """, (
                job_id,
                config["symbol"],
                config["name"],
                json.dumps(config),
                json.dumps(schedule),
                email,
                token,
            ))
        conn.commit()
    logger.info("PG: saved job %s", job_id)


def pg_load_jobs() -> list:
    """Return all scheduled jobs as a list of dicts with parsed config/schedule."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM scheduled_jobs")
            rows = cur.fetchall()
    result = []
    for row in rows:
        try:
            result.append({
                "job_id":   row["job_id"],
                "config":   json.loads(row["config_json"]),
                "schedule": json.loads(row["schedule_json"]),
                "email":    row["email"],
                "token":    row["token"],
            })
        except Exception as exc:
            logger.error("PG: skipping malformed job %s: %s", row["job_id"], exc)
    logger.info("PG: loaded %d job(s)", len(result))
    return result


def pg_delete_job(job_id: str) -> None:
    """Delete a scheduled job by ID."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scheduled_jobs WHERE job_id = %s", (job_id,))
        conn.commit()
    logger.info("PG: deleted job %s", job_id)
