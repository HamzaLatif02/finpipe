import json
import logging
import os
import sys
from pathlib import Path

from flask import Blueprint, jsonify, request

# Root pipeline modules use CWD-relative paths (e.g. data/raw/).
# Flask must be started from the project root for those paths to resolve.
# We also insert the project root onto sys.path so imports work regardless
# of where Python's working directory is set.
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _ROOT)

from fetcher import fetch_data
from cleaner import clean_data
from db import insert_prices, insert_info, init_db, list_assets
from analysis import run_analysis
from charts import generate_charts

pipeline_bp = Blueprint("pipeline", __name__)
logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"symbol", "name", "asset_type", "currency", "period", "interval"}

# Fields surfaced from the raw Yahoo Finance info blob
_INFO_FIELDS = (
    "longName", "shortName", "quoteType", "currency", "exchange",
    "sector", "industry", "marketCap", "website", "country",
)


def _latest_value(price_series) -> dict:
    """Extract the most recent close price and date from a price_series DataFrame."""
    idx = price_series.index[-1]
    date_str = str(idx.date()) if hasattr(idx, "date") else str(idx)
    row = price_series.iloc[-1]
    close = row.get("close", row.get("Close")) if hasattr(row, "get") else (
        row["close"] if "close" in price_series.columns else row["Close"]
    )
    return {
        "date":  date_str,
        "close": round(float(close), 6) if close is not None else None,
    }


def _chart_urls(paths: list, symbol: str) -> list:
    """Convert local chart file paths to API URL stems."""
    return [f"/api/reports/charts/{Path(p).stem}" for p in paths]


@pipeline_bp.post("/run")
def run_pipeline():
    body = request.get_json(silent=True) or {}

    missing = _REQUIRED_FIELDS - body.keys()
    if missing:
        return jsonify({
            "status": "error",
            "error":  f"Missing required fields: {', '.join(sorted(missing))}",
        }), 400

    config = {field: body[field] for field in _REQUIRED_FIELDS}
    symbol = config["symbol"]

    # ------------------------------------------------------------------ #
    # Stage 1 — init_db                                                    #
    # ------------------------------------------------------------------ #
    try:
        init_db()
    except Exception as exc:
        logger.exception("init_db failed for %s", symbol)
        return jsonify({"status": "error", "stage": "init_db", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Stage 2 — fetch_data                                                 #
    # ------------------------------------------------------------------ #
    try:
        fetched = fetch_data(config)
        prices_df = fetched["prices"]
        info_dict = fetched["info"]
    except Exception as exc:
        logger.exception("fetch_data failed for %s", symbol)
        return jsonify({"status": "error", "stage": "fetch_data", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Stage 3 — clean_data                                                 #
    # ------------------------------------------------------------------ #
    try:
        cleaned_df = clean_data(config)
    except Exception as exc:
        logger.exception("clean_data failed for %s", symbol)
        return jsonify({"status": "error", "stage": "clean_data", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Stage 4 — insert to DB                                               #
    # ------------------------------------------------------------------ #
    try:
        insert_prices(config, cleaned_df)
        insert_info(config, info_dict)
    except Exception as exc:
        logger.exception("db insert failed for %s", symbol)
        return jsonify({"status": "error", "stage": "db_insert", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Stage 5 — analysis                                                   #
    # ------------------------------------------------------------------ #
    try:
        analysis = run_analysis(config)
    except Exception as exc:
        logger.exception("run_analysis failed for %s", symbol)
        return jsonify({"status": "error", "stage": "run_analysis", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Stage 6 — charts                                                     #
    # ------------------------------------------------------------------ #
    try:
        chart_paths = generate_charts(config, analysis)
    except Exception as exc:
        logger.exception("generate_charts failed for %s", symbol)
        return jsonify({"status": "error", "stage": "generate_charts", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Stage 7 — save config                                                #
    # ------------------------------------------------------------------ #
    try:
        config_path = Path(_ROOT) / "data" / f"{symbol}_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as exc:
        logger.exception("config save failed for %s", symbol)
        return jsonify({"status": "error", "stage": "save_config", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Build response                                                        #
    # ------------------------------------------------------------------ #
    raw_info = analysis.get("asset_info") or {}
    selected_info = {k: raw_info[k] for k in _INFO_FIELDS if raw_info.get(k) is not None}

    return jsonify({
        "status":        "success",
        "symbol":        symbol,
        "summary_stats": analysis.get("summary_stats") or {},
        "chart_urls":    _chart_urls(chart_paths, symbol),
        "latest_value":  _latest_value(analysis["price_series"]),
        "asset_info":    selected_info,
    })


@pipeline_bp.get("/status")
def status():
    try:
        init_db()  # ensure tables exist even before any pipeline run
        df = list_assets()
        cols = ["symbol", "name", "asset_type", "run_at", "row_count"]
        present = [c for c in cols if c in df.columns]
        assets = df[present].to_dict(orient="records")
        return jsonify({"assets": assets})
    except Exception as exc:
        logger.exception("list_assets failed")
        return jsonify({"error": str(exc)}), 500
