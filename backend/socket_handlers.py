"""
Flask-SocketIO event handlers for real-time pipeline and comparison progress.

Import order matters:
  app.py  defines  socketio  →  imports this module at the bottom
  This module does  from app import socketio  (module already in sys.cache)
  progress.py  also does  from app import socketio  (same cached module)
"""
import json
import logging
import os
import sys
import threading
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from flask_socketio import join_room, emit  # noqa: E402
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


# ── Connection lifecycle ───────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    logger.info("[WS] client connected: %s", getattr(threading.current_thread(), "name", "?"))


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

    symbol = config.get("symbol", "?").strip().upper()
    config["symbol"] = symbol

    def run():
        try:
            emit_progress(run_id, "init", "Initialising", 0)
            init_db()

            emit_progress(run_id, "fetch", "Fetching market data", 15)
            fetched   = fetch_data(config)
            prices_df = fetched["prices"]
            info_dict = fetched["info"]

            emit_progress(run_id, "clean", "Cleaning data", 30)
            cleaned_df = clean_data(config)

            emit_progress(run_id, "store", "Storing to database", 42)
            insert_prices(config, cleaned_df)
            insert_info(config, info_dict)

            emit_progress(run_id, "analyse", "Running analysis", 55)
            analysis = run_analysis(config)

            emit_progress(run_id, "charts", "Generating charts", 70)
            chart_paths = generate_charts(config, analysis)

            emit_progress(run_id, "report", "Building PDF report", 85)
            generate_report(config, analysis, chart_paths)

            emit_progress(run_id, "complete", "Complete", 100)

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

    def run():
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
            # (already stored above; this step communicates DB flush)

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

    threading.Thread(target=run, daemon=True).start()
