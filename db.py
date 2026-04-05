import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import DB_PATH as _DB_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path(_DB_PATH)


def _connect() -> sqlite3.Connection:
    """Open and return a connection to the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _table_name(symbol: str) -> str:
    """Convert a ticker symbol to a safe SQL table name."""
    safe = re.sub(r"[^a-z0-9]", "_", symbol.lower())
    return f"prices_{safe}"


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. init_db
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create data/reporting.db and all required tables."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS asset_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT    NOT NULL,
                name        TEXT,
                asset_type  TEXT,
                period      TEXT,
                interval    TEXT,
                run_at      TEXT    NOT NULL,
                row_count   INTEGER,
                config_json TEXT
            );

            CREATE TABLE IF NOT EXISTS asset_info (
                symbol      TEXT PRIMARY KEY,
                name        TEXT,
                asset_type  TEXT,
                currency    TEXT,
                info_json   TEXT,
                updated_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                job_id        TEXT PRIMARY KEY,
                config_json   TEXT    NOT NULL,
                schedule_json TEXT    NOT NULL,
                email         TEXT    NOT NULL,
                token         TEXT    NOT NULL,
                created_at    TEXT    NOT NULL
            );
        """)
    logger.info("Database initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# 2. insert_prices
# ---------------------------------------------------------------------------

def insert_prices(config: dict, df: pd.DataFrame) -> None:
    """Create prices_{symbol} table if needed, insert rows, log to asset_runs."""
    symbol = config["symbol"]
    table = _table_name(symbol)

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            date              TEXT    UNIQUE NOT NULL,
            open              REAL,
            high              REAL,
            low               REAL,
            close             REAL,
            volume            REAL,
            daily_return      REAL,
            cumulative_return REAL,
            typical_price     REAL,
            price_range       REAL,
            vwap              REAL,
            inserted_at       TEXT    NOT NULL
        );
    """

    now = _now()

    # Normalise the Date column to plain date strings (YYYY-MM-DD).
    dates = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

    rows = [
        (
            dates.iloc[i],
            _float(df, i, "Open"),
            _float(df, i, "High"),
            _float(df, i, "Low"),
            _float(df, i, "Close"),
            _float(df, i, "Volume"),
            _float(df, i, "daily_return"),
            _float(df, i, "cumulative_return"),
            _float(df, i, "typical_price"),
            _float(df, i, "price_range"),
            _float(df, i, "vwap"),
            now,
        )
        for i in range(len(df))
    ]

    insert_sql = f"""
        INSERT OR IGNORE INTO {table}
            (date, open, high, low, close, volume,
             daily_return, cumulative_return, typical_price, price_range, vwap,
             inserted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    run_sql = """
        INSERT INTO asset_runs
            (symbol, name, asset_type, period, interval, run_at, row_count, config_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    with _connect() as conn:
        conn.execute(create_sql)
        conn.executemany(insert_sql, rows)
        conn.execute(run_sql, (
            symbol,
            config.get("name"),
            config.get("asset_type"),
            config.get("period"),
            config.get("interval"),
            now,
            len(df),
            json.dumps(config),
        ))

    logger.info("Inserted %d rows into %s, logged run to asset_runs.", len(df), table)


def _float(df: pd.DataFrame, i: int, col: str):
    """Return float value or None if the column is missing or NaN."""
    if col not in df.columns:
        return None
    val = df[col].iloc[i]
    try:
        return None if pd.isna(val) else float(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 3. insert_info
# ---------------------------------------------------------------------------

def insert_info(config: dict, info: dict) -> None:
    """Upsert asset metadata into asset_info."""
    sql = """
        INSERT OR REPLACE INTO asset_info
            (symbol, name, asset_type, currency, info_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    with _connect() as conn:
        conn.execute(sql, (
            config["symbol"],
            config.get("name"),
            config.get("asset_type"),
            config.get("currency"),
            json.dumps(info, default=str),
            _now(),
        ))
    logger.info("Upserted asset_info for %s.", config["symbol"])


# ---------------------------------------------------------------------------
# 4. query_prices
# ---------------------------------------------------------------------------

def query_prices(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
) -> pd.DataFrame:
    """Query the prices table for a symbol with optional date range filters.

    Returns a DataFrame with Date as a datetime index.
    """
    table = _table_name(symbol)
    conditions = []
    params = []

    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM {table} {where} ORDER BY date ASC"

    with _connect() as conn:
        try:
            df = pd.read_sql_query(sql, conn, params=params, parse_dates=["date"])
        except Exception as exc:
            logger.error("Could not query %s: %s", table, exc)
            return pd.DataFrame()

    df.rename(columns={"date": "Date"}, inplace=True)
    df.set_index("Date", inplace=True)
    logger.info("Queried %d rows from %s.", len(df), table)
    return df


# ---------------------------------------------------------------------------
# 5. list_assets
# ---------------------------------------------------------------------------

def list_assets() -> pd.DataFrame:
    """Return all rows from asset_runs, newest first."""
    sql = "SELECT * FROM asset_runs ORDER BY run_at DESC"
    with _connect() as conn:
        df = pd.read_sql_query(sql, conn)
    logger.info("Listed %d asset run(s).", len(df))
    return df


# ---------------------------------------------------------------------------
# 6. scheduled_jobs persistence
# ---------------------------------------------------------------------------

def save_scheduled_job(job_id: str, config: dict, schedule: dict, email: str, token: str) -> None:
    """Insert or replace a scheduled job record."""
    sql = """
        INSERT OR REPLACE INTO scheduled_jobs
            (job_id, config_json, schedule_json, email, token, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    with _connect() as conn:
        conn.execute(sql, (
            job_id,
            json.dumps(config),
            json.dumps(schedule),
            email,
            token,
            _now(),
        ))
    logger.info("Saved scheduled job: %s", job_id)


def load_scheduled_jobs() -> list:
    """Return all scheduled jobs as a list of dicts with parsed config/schedule."""
    sql = "SELECT job_id, config_json, schedule_json, email, token FROM scheduled_jobs"
    with _connect() as conn:
        rows = conn.execute(sql).fetchall()
    result = []
    for job_id, config_json, schedule_json, email, token in rows:
        try:
            result.append({
                "job_id":   job_id,
                "config":   json.loads(config_json),
                "schedule": json.loads(schedule_json),
                "email":    email,
                "token":    token,
            })
        except Exception as exc:
            logger.error("Skipping malformed scheduled job %s: %s", job_id, exc)
    logger.info("Loaded %d scheduled job(s) from DB", len(result))
    return result


def delete_scheduled_job(job_id: str) -> bool:
    """Delete a scheduled job; returns True if a row was removed."""
    sql = "DELETE FROM scheduled_jobs WHERE job_id = ?"
    with _connect() as conn:
        cursor = conn.execute(sql, (job_id,))
        deleted = cursor.rowcount > 0
    if deleted:
        logger.info("Deleted scheduled job: %s", job_id)
    return deleted


# ---------------------------------------------------------------------------
# Main guard
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print(f"Database ready at {DB_PATH}")
