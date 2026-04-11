import json
import logging
import os
import re
import sys
from pathlib import Path

from flask import jsonify, request
from flask_smorest import Blueprint

# Root pipeline modules use CWD-relative paths (e.g. data/raw/).
# Flask must be started from the project root for those paths to resolve.
# We also insert the project root onto sys.path so imports work regardless
# of where Python's working directory is set.
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _ROOT)

from fetcher import fetch_data
from cleaner import clean_data
from db import (
    insert_prices, insert_info, init_db, list_assets,
    get_cached_report, save_cached_report,
)
from analysis import run_analysis
from charts import generate_charts
from report import generate_report
from scheduler import _send_email  # reuse the shared email helper
from extensions import limiter
from schemas import (
    PipelineRunResponseSchema, PipelineStatusResponseSchema, ErrorResponseSchema,
)

pipeline_bp = Blueprint(
    "Pipeline", __name__,
    description="Run the full financial analysis pipeline for a single asset.",
)
logger = logging.getLogger(__name__)

_REQUIRED_FIELDS  = {"symbol", "name", "asset_type", "currency", "period", "interval"}
_SYMBOL_RE        = re.compile(r'^[A-Z0-9.\-\^=]{1,20}$')
_ALLOWED_EMAIL    = os.getenv("REPORT_RECIPIENT", "").strip().lower()

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
@pipeline_bp.response(200, PipelineRunResponseSchema())
@pipeline_bp.alt_response(400, schema=ErrorResponseSchema(), description="Validation error")
@pipeline_bp.alt_response(429, schema=ErrorResponseSchema(), description="Rate limit exceeded")
@pipeline_bp.alt_response(500, schema=ErrorResponseSchema(), description="Pipeline stage failed")
@pipeline_bp.doc(
    summary="Run financial analysis pipeline",
    description=(
        "Fetches market data from Yahoo Finance, cleans it, runs statistical analysis, "
        "generates charts, and builds a PDF report. "
        "Results are cached for 1 hour — pass `bypass_cache: true` or the "
        "`X-Cache-Bypass: true` header to force a fresh run. "
        "**Rate limit:** 3/min · 10/hr · 30/day."
    ),
    requestBody={
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["symbol", "name", "asset_type", "currency", "period", "interval"],
                    "properties": {
                        "symbol":       {"type": "string",  "example": "AAPL"},
                        "name":         {"type": "string",  "example": "Apple Inc."},
                        "asset_type":   {"type": "string",  "example": "Stocks"},
                        "currency":     {"type": "string",  "example": "USD"},
                        "period":       {"type": "string",  "example": "1y",
                                         "description": "Use 'custom' to supply start_date/end_date."},
                        "interval":     {"type": "string",  "example": "1d"},
                        "start_date":   {"type": "string",  "example": "2023-01-01",
                                         "description": "Required when period='custom'."},
                        "end_date":     {"type": "string",  "example": "2024-01-01",
                                         "description": "Required when period='custom'."},
                        "email":        {"type": "string",  "example": "user@example.com",
                                         "description": "If provided, the PDF is emailed instead of cached."},
                        "bypass_cache": {"type": "boolean", "example": False},
                    },
                }
            }
        },
    },
)
@limiter.limit("30 per day;10 per hour;3 per minute")
def run_pipeline():
    body = request.get_json(silent=True) or {}

    missing = _REQUIRED_FIELDS - body.keys()
    if missing:
        return jsonify({
            "status": "error",
            "error":  f"Missing required fields: {', '.join(sorted(missing))}",
        }), 400

    config = {field: body[field] for field in _REQUIRED_FIELDS}
    symbol = config["symbol"].strip().upper()
    config["symbol"] = symbol

    if not _SYMBOL_RE.match(symbol):
        return jsonify({
            "status": "error",
            "error":  "Invalid symbol. Use 1–20 characters: letters, digits, . - ^ =",
        }), 400

    if config["period"] == "custom":
        start_date = body.get("start_date", "").strip()
        end_date   = body.get("end_date", "").strip()
        if not start_date or not end_date:
            return jsonify({
                "status": "error",
                "error":  "start_date and end_date are required when period is 'custom'",
            }), 400
        config["start_date"] = start_date
        config["end_date"]   = end_date

    raw_email = (body.get("email") or "").strip().lower()
    if raw_email and (_ALLOWED_EMAIL and raw_email != _ALLOWED_EMAIL):
        return jsonify({
            "status": "error",
            "error":  "Email address not permitted.",
        }), 403
    email = raw_email or None

    # ------------------------------------------------------------------ #
    # Cache check (skip when bypass_cache=true or email delivery)          #
    # ------------------------------------------------------------------ #
    bypass_cache = (
        request.headers.get("X-Cache-Bypass", "").lower() == "true"
        or body.get("bypass_cache") is True
    )
    if not bypass_cache and not email:
        cached = get_cached_report(config)
        if cached:
            logger.info(
                "Serving cached report for %s (age: %.1f min)",
                symbol, cached["age_minutes"],
            )
            cached_result = cached["result"]
            chart_urls = [
                f"/api/reports/charts/{os.path.basename(p)}"
                for p in cached["chart_paths"]
            ]
            return jsonify({
                "status":        "success",
                "cache_hit":     True,
                "cached_at":     cached["cached_at"],
                "age_minutes":   cached["age_minutes"],
                "symbol":        symbol,
                "summary_stats": cached_result.get("summary_stats", {}),
                "chart_urls":    chart_urls,
                "latest_value":  cached_result.get("latest_value"),
                "asset_info":    cached_result.get("asset_info", {}),
            })

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
        prices_df = fetched["prices"]  # noqa: F841 — fetched for side-effects in fetch_data
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
    # Stage 7 — generate PDF report                                        #
    # ------------------------------------------------------------------ #
    try:
        pdf_path = generate_report(config, analysis, chart_paths)
    except Exception as exc:
        logger.exception("generate_report failed for %s", symbol)
        return jsonify({"status": "error", "stage": "generate_report", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Stage 7b — save to cache (skip for email-triggered runs)             #
    # ------------------------------------------------------------------ #
    if not email:
        try:
            _raw_info = analysis.get("asset_info") or {}
            cache_result = {
                "summary_stats": analysis.get("summary_stats") or {},
                "latest_value":  _latest_value(analysis["price_series"]),
                "asset_info":    {k: _raw_info[k] for k in _INFO_FIELDS if _raw_info.get(k) is not None},
            }
            save_cached_report(config, cache_result, chart_paths, pdf_path)
        except Exception as exc:
            logger.warning("Cache save failed for %s: %s", symbol, exc)

    # ------------------------------------------------------------------ #
    # Stage 7c — email PDF if requested                                    #
    # ------------------------------------------------------------------ #
    if email:
        try:
            subject = f"Financial Report: {config['name']} ({symbol})"
            body_text = (
                f"Please find attached the financial report for "
                f"{config['name']} ({symbol}).\n\n"
                f"Period: {config.get('period', '')}  |  "
                f"Interval: {config.get('interval', '')}\n\n"
                "Generated by Financial Pipeline. Not financial advice."
            )
            _send_email(email, subject, body_text, pdf_path)
        except Exception as exc:
            logger.exception("email send failed for %s → %s", symbol, email)
            return jsonify({"status": "error", "stage": "send_email", "error": str(exc)}), 500

    # ------------------------------------------------------------------ #
    # Stage 8 — save config                                                #
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
        "cache_hit":     False,
        "symbol":        symbol,
        "summary_stats": analysis.get("summary_stats") or {},
        "chart_urls":    _chart_urls(chart_paths, symbol),
        "latest_value":  _latest_value(analysis["price_series"]),
        "asset_info":    selected_info,
    })


@pipeline_bp.get("/status")
@pipeline_bp.response(200, PipelineStatusResponseSchema())
@pipeline_bp.alt_response(500, schema=ErrorResponseSchema())
def status():
    """List all assets that have been processed by the pipeline."""
    try:
        init_db()
        df = list_assets()
        cols = ["symbol", "name", "asset_type", "run_at", "row_count"]
        present = [c for c in cols if c in df.columns]
        assets = df[present].to_dict(orient="records")
        return jsonify({"assets": assets})
    except Exception as exc:
        logger.exception("list_assets failed")
        return jsonify({"error": str(exc)}), 500
