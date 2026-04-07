"""
Flask-SocketIO event handlers for real-time pipeline and comparison progress.

Import order matters:
  app.py  defines  socketio  →  imports this module at the bottom
  This module does  from app import socketio  (module already in sys.cache)
  progress.py  also does  from app import socketio  (same cached module)
"""
import logging
import os
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from flask_socketio import join_room, emit  # noqa: E402
from flask import request as flask_request  # noqa: E402
from app import socketio                    # noqa: E402
from progress import emit_progress          # noqa: E402

from fetcher             import fetch_data
from cleaner             import clean_data
from db                  import insert_prices, insert_info, init_db
from analysis            import run_analysis
from charts              import generate_charts
from report              import generate_report
from comparison_analysis import run_comparison
from comparison_charts   import generate_comparison_charts
from comparison_report   import generate_comparison_report

logger = logging.getLogger(__name__)

# ── WebSocket rate limiter ────────────────────────────────────────────────────
# Simple in-memory sliding-window counter (pipeline + comparison combined).
# Limits: 10 per minute, 30 per hour, per IP.

_ws_lock    = threading.Lock()
_ws_counts  = defaultdict(list)   # ip → [timestamp, ...]

_WS_LIMITS = [
    (60,    10),   # 10 per minute
    (3600,  30),   # 30 per hour
]


def _ws_check_rate_limit(ip: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds).

    Prunes old timestamps and checks all window limits.  If any limit is
    exceeded, returns (False, seconds_until_oldest_entry_expires).
    """
    now = time.time()
    with _ws_lock:
        timestamps = _ws_counts[ip]
        # Prune entries older than the largest window (1 hour)
        _ws_counts[ip] = [t for t in timestamps if now - t < 3600]
        timestamps = _ws_counts[ip]

        for window, limit in _WS_LIMITS:
            recent = [t for t in timestamps if now - t < window]
            if len(recent) >= limit:
                oldest_in_window = min(recent)
                retry_after = int(window - (now - oldest_in_window)) + 1
                return False, retry_after

        # Record this new call
        _ws_counts[ip].append(now)
        return True, 0


_INFO_FIELDS = (
    "longName", "shortName", "quoteType", "currency", "exchange",
    "sector", "industry", "marketCap", "website", "country",
)


def _latest_value(price_series) -> dict:
    idx      = price_series.index[-1]
    date_str = str(idx.date()) if hasattr(idx, "date") else str(idx)
    row      = price_series.iloc[-1]
    close    = row.get("close", row.get("Close")) if hasattr(row, "get") else (
        row["close"] if "close" in price_series.columns else row["Close"]
    )
    return {
        "date":  date_str,
        "close": round(float(close), 6) if close is not None else None,
    }


def _chart_urls_for(paths: list) -> list:
    return [f"/api/reports/charts/{Path(p).stem}" for p in paths]


def _start_keepalive(run_id: str, stop_event: threading.Event, interval: int = 15):
    """Emit a ws_ping to the run's room every `interval` seconds.

    This prevents Render's proxy (and other reverse proxies) from closing the
    WebSocket connection as idle during long-running pipeline stages such as
    AI analysis which can take 30-40 seconds without a socket write.
    """
    def _loop():
        while not stop_event.wait(interval):
            socketio.emit("ws_ping", {"run_id": run_id}, room=run_id)
            logger.debug("[WS] keepalive ping → run_id=%s", run_id)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


# ── Connection lifecycle ───────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    logger.info("[WS] client connected")


@socketio.on("disconnect")
def on_disconnect():
    logger.info("[WS] client disconnected")


# ── Room join ─────────────────────────────────────────────────────────────────

@socketio.on("join")
def on_join(data):
    run_id = (data or {}).get("run_id")
    if run_id:
        join_room(run_id)
        emit("joined", {"run_id": run_id})
        logger.info("[WS] joined room %s", run_id)


# ── Pipeline run ──────────────────────────────────────────────────────────────

@socketio.on("start_pipeline")
def on_start_pipeline(data):
    run_id = (data or {}).get("run_id")
    config = (data or {}).get("config") or {}
    if not run_id or not config:
        emit("pipeline_error", {"error": "run_id and config are required"})
        return

    client_ip = flask_request.remote_addr or "unknown"
    allowed, retry_after = _ws_check_rate_limit(client_ip)
    if not allowed:
        emit("pipeline_error", {
            "run_id":      run_id,
            "error":       f"Rate limit exceeded. Try again in {retry_after} seconds.",
            "rate_limited": True,
            "retry_after": retry_after,
        })
        return

    symbol = config.get("symbol", "?").strip().upper()
    config["symbol"] = symbol

    def run():
        stop_ka = threading.Event()
        _start_keepalive(run_id, stop_ka)
        try:
            emit_progress(run_id, "init",    "Initialising",          0)
            init_db()

            emit_progress(run_id, "fetch",   "Fetching market data",  15)
            fetched    = fetch_data(config)
            info_dict  = fetched["info"]

            emit_progress(run_id, "clean",   "Cleaning data",         30)
            cleaned_df = clean_data(config)

            emit_progress(run_id, "store",   "Storing to database",   42)
            insert_prices(config, cleaned_df)
            insert_info(config, info_dict)

            emit_progress(run_id, "analyse", "Running analysis",      55)
            analysis = run_analysis(config)

            emit_progress(run_id, "charts",  "Generating charts",     70)
            chart_paths = generate_charts(config, analysis)

            emit_progress(run_id, "report",  "Building PDF report",   85)
            generate_report(config, analysis, chart_paths)

            emit_progress(run_id, "complete", "Complete",             100)

            raw_info      = analysis.get("asset_info") or {}
            selected_info = {k: raw_info[k] for k in _INFO_FIELDS if raw_info.get(k) is not None}

            socketio.emit("pipeline_complete", {
                "run_id":        run_id,
                "status":        "success",
                "symbol":        symbol,
                "name":          config.get("name", symbol),
                "asset_type":    config.get("asset_type", ""),
                "summary_stats": analysis.get("summary_stats") or {},
                "chart_urls":    _chart_urls_for(chart_paths),
                "latest_value":  _latest_value(analysis["price_series"]),
                "asset_info":    selected_info,
            }, room=run_id)

        except Exception as exc:
            logger.exception("[WS] pipeline_error run_id=%s", run_id)
            socketio.emit("pipeline_error", {"run_id": run_id, "error": str(exc)}, room=run_id)
        finally:
            stop_ka.set()

    threading.Thread(target=run, daemon=True).start()


# ── Comparison run ────────────────────────────────────────────────────────────

@socketio.on("start_comparison")
def on_start_comparison(data):
    run_id   = (data or {}).get("run_id")
    config_a = (data or {}).get("config_a") or {}
    config_b = (data or {}).get("config_b") or {}
    if not run_id or not config_a or not config_b:
        emit("pipeline_error", {"error": "run_id, config_a and config_b are required"})
        return

    client_ip = flask_request.remote_addr or "unknown"
    allowed, retry_after = _ws_check_rate_limit(client_ip)
    if not allowed:
        emit("pipeline_error", {
            "run_id":       run_id,
            "error":        f"Rate limit exceeded. Try again in {retry_after} seconds.",
            "rate_limited": True,
            "retry_after":  retry_after,
        })
        return

    def run():
        stop_ka = threading.Event()
        _start_keepalive(run_id, stop_ka)
        try:
            sym_a = config_a.get("symbol", "A").strip().upper()
            sym_b = config_b.get("symbol", "B").strip().upper()
            config_a["symbol"] = sym_a
            config_b["symbol"] = sym_b

            emit_progress(run_id, "init",    "Initialising",                 0)
            init_db()

            emit_progress(run_id, "fetch_a", f"Fetching data for {sym_a}",  10)
            fetched_a  = fetch_data(config_a)
            cleaned_a  = clean_data(config_a)
            insert_prices(config_a, cleaned_a)
            insert_info(config_a, fetched_a["info"])

            emit_progress(run_id, "fetch_b", f"Fetching data for {sym_b}",  22)
            fetched_b  = fetch_data(config_b)
            cleaned_b  = clean_data(config_b)
            insert_prices(config_b, cleaned_b)
            insert_info(config_b, fetched_b["info"])

            emit_progress(run_id, "store",   "Storing to database",          34)

            emit_progress(run_id, "analyse", "Running comparison analysis",  46)
            comparison = run_comparison(config_a, config_b)

            emit_progress(run_id, "charts",  "Generating comparison charts", 62)
            chart_paths = generate_comparison_charts(config_a, config_b, comparison)

            emit_progress(run_id, "report",  "Building combined PDF",        78)
            generate_comparison_report(config_a, config_b, comparison, chart_paths)

            emit_progress(run_id, "complete", "Complete",                   100)

            chart_urls = [f"/api/reports/charts/{Path(p).name}" for p in chart_paths]

            socketio.emit("comparison_complete", {
                "run_id":       run_id,
                "status":       "success",
                "symbol_a":     sym_a,
                "symbol_b":     sym_b,
                "name_a":       comparison["name_a"],
                "name_b":       comparison["name_b"],
                "correlation":  comparison["correlation"],
                "metrics":      comparison["metrics"],
                "cum_returns":  comparison["cum_returns"],
                "overlap_days": comparison["overlap_days"],
                "chart_urls":   chart_urls,
                "period":       config_a.get("period", ""),
                "interval":     config_a.get("interval", ""),
            }, room=run_id)

        except Exception as exc:
            logger.exception("[WS] comparison_error run_id=%s", run_id)
            socketio.emit("pipeline_error", {"run_id": run_id, "error": str(exc)}, room=run_id)
        finally:
            stop_ka.set()

    threading.Thread(target=run, daemon=True).start()
