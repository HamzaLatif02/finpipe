import logging
import os
import sys
from pathlib import Path

from flask import jsonify, request, send_from_directory
from flask_smorest import Blueprint

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from comparison_analysis import run_comparison           # noqa: E402
from comparison_charts   import generate_comparison_charts  # noqa: E402
from comparison_report   import generate_comparison_report  # noqa: E402
from fetcher import fetch_data                           # noqa: E402
from cleaner import clean_data                           # noqa: E402
from db      import (                                    # noqa: E402
    insert_prices, insert_info, init_db,
    get_cached_report, save_cached_report,
)
from extensions import limiter                           # noqa: E402
from schemas import (                                    # noqa: E402
    ComparisonRunResponseSchema, ErrorResponseSchema,
)

comparison_bp = Blueprint(
    "Comparison", __name__,
    description="Side-by-side comparison of two assets over the same period.",
)
logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(_ROOT, "data")

_REQUIRED_CONFIG = {"symbol", "name", "asset_type", "currency", "period", "interval"}


@comparison_bp.post("/run")
@comparison_bp.response(200, ComparisonRunResponseSchema())
@comparison_bp.alt_response(400, schema=ErrorResponseSchema(), description="Validation error")
@comparison_bp.alt_response(429, schema=ErrorResponseSchema(), description="Rate limit exceeded")
@comparison_bp.alt_response(500, schema=ErrorResponseSchema(), description="Pipeline stage failed")
@comparison_bp.doc(
    summary="Run asset comparison pipeline",
    description=(
        "Fetches and analyses data for two assets in parallel, then generates "
        "correlation metrics, cumulative return charts, and a combined PDF report. "
        "Both assets must share the same `period` and `interval`. "
        "Results are cached for 1 hour. "
        "**Rate limit:** 2/min · 5/hr · 15/day."
    ),
    requestBody={
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["config_a", "config_b"],
                    "properties": {
                        "config_a": {
                            "type": "object",
                            "description": "Config for the first asset",
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
                        "config_b": {
                            "type": "object",
                            "description": "Config for the second asset (same period/interval required)",
                            "required": ["symbol", "name", "asset_type", "currency", "period", "interval"],
                            "properties": {
                                "symbol":     {"type": "string", "example": "MSFT"},
                                "name":       {"type": "string", "example": "Microsoft Corp."},
                                "asset_type": {"type": "string", "example": "Stocks"},
                                "currency":   {"type": "string", "example": "USD"},
                                "period":     {"type": "string", "example": "1y"},
                                "interval":   {"type": "string", "example": "1d"},
                            },
                        },
                        "bypass_cache": {"type": "boolean", "example": False},
                    },
                }
            }
        },
    },
)
@limiter.limit("15 per day;5 per hour;2 per minute")
def run():
    body = request.get_json(silent=True) or {}
    config_a = body.get("config_a") or {}
    config_b = body.get("config_b") or {}

    if not config_a or not config_b:
        return jsonify({"error": "Both config_a and config_b are required."}), 400

    missing_a = _REQUIRED_CONFIG - config_a.keys()
    missing_b = _REQUIRED_CONFIG - config_b.keys()
    if missing_a:
        return jsonify({"error": f"config_a missing fields: {', '.join(sorted(missing_a))}."}), 400
    if missing_b:
        return jsonify({"error": f"config_b missing fields: {', '.join(sorted(missing_b))}."}), 400

    sym_a = config_a["symbol"]
    sym_b = config_b["symbol"]

    if sym_a == sym_b:
        return jsonify({"error": "Cannot compare an asset with itself."}), 400

    if config_a["period"] != config_b["period"] or config_a["interval"] != config_b["interval"]:
        return jsonify({
            "error": "Both assets must use the same period and interval for a meaningful comparison."
        }), 400

    # ------------------------------------------------------------------ #
    # Cache check                                                          #
    # ------------------------------------------------------------------ #
    bypass_cache = (
        request.headers.get("X-Cache-Bypass", "").lower() == "true"
        or body.get("bypass_cache") is True
    )
    if not bypass_cache:
        comparison_cache_config = {
            "symbol":     f"{sym_a}_vs_{sym_b}",
            "name":       f"{config_a.get('name', sym_a)} vs {config_b.get('name', sym_b)}",
            "asset_type": "Comparison",
            "currency":   config_a.get("currency", ""),
            "period":     config_a.get("period", ""),
            "interval":   config_a.get("interval", ""),
            "start_date": config_a.get("start_date"),
            "end_date":   config_a.get("end_date"),
        }
        cached = get_cached_report(comparison_cache_config)
        if cached:
            cached_result = cached["result"]
            chart_urls = [
                f"/api/reports/charts/{os.path.basename(p)}"
                for p in cached["chart_paths"]
            ]
            return jsonify({
                **cached_result,
                "status":      "success",
                "cache_hit":   True,
                "cached_at":   cached["cached_at"],
                "age_minutes": cached["age_minutes"],
                "chart_urls":  chart_urls,
            })

    stage = "init"
    try:
        stage = "db_init"
        init_db()

        stage = "fetch_a"
        fetched_a = fetch_data(config_a)
        df_a = clean_data(config_a)
        insert_prices(config_a, df_a)
        insert_info(config_a, fetched_a["info"])

        stage = "fetch_b"
        fetched_b = fetch_data(config_b)
        df_b = clean_data(config_b)
        insert_prices(config_b, df_b)
        insert_info(config_b, fetched_b["info"])

        stage = "analysis"
        comparison = run_comparison(config_a, config_b)

        stage = "charts"
        chart_paths = generate_comparison_charts(config_a, config_b, comparison)

        stage = "report"
        generate_comparison_report(config_a, config_b, comparison, chart_paths)

    except ValueError as exc:
        logger.warning("Comparison validation error at %s: %s", stage, exc)
        return jsonify({"status": "error", "stage": stage, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Comparison failed at stage: %s", stage)
        return jsonify({"status": "error", "stage": stage, "error": str(exc)}), 500

    chart_urls = [f"/api/reports/charts/{Path(p).name}" for p in chart_paths]
    pdf_path   = str(Path(_DATA_DIR) / f"{sym_a}_vs_{sym_b}_comparison_report.pdf")

    response_data = {
        "symbol_a":     sym_a,
        "symbol_b":     sym_b,
        "name_a":       comparison["name_a"],
        "name_b":       comparison["name_b"],
        "correlation":  comparison["correlation"],
        "metrics":      comparison["metrics"],
        "cum_returns":  comparison["cum_returns"],
        "overlap_days": comparison["overlap_days"],
        "pdf_url":      f"/api/comparison/pdf/{sym_a}/{sym_b}",
    }

    # Save to cache
    if not bypass_cache:
        try:
            save_cached_report(comparison_cache_config, response_data, chart_paths, pdf_path)
        except Exception as exc:
            logger.warning("Comparison cache save failed: %s", exc)

    return jsonify({
        "status":    "success",
        "cache_hit": False,
        **response_data,
        "chart_urls": chart_urls,
    })


@comparison_bp.get("/pdf/<symbol_a>/<symbol_b>")
@comparison_bp.alt_response(404, schema=ErrorResponseSchema())
def view_pdf(symbol_a: str, symbol_b: str):
    """Serve the comparison PDF inline in the browser."""
    filename = f"{symbol_a}_vs_{symbol_b}_comparison_report.pdf"
    data_dir = Path(_DATA_DIR)
    if not (data_dir / filename).is_file():
        return jsonify({"error": f"Comparison report for '{symbol_a} vs {symbol_b}' not found."}), 404
    return send_from_directory(
        str(data_dir.resolve()), filename,
        mimetype="application/pdf", as_attachment=False,
    )


@comparison_bp.get("/download/<symbol_a>/<symbol_b>")
@comparison_bp.alt_response(404, schema=ErrorResponseSchema())
def download_pdf(symbol_a: str, symbol_b: str):
    """Download the comparison PDF as an attachment."""
    filename = f"{symbol_a}_vs_{symbol_b}_comparison_report.pdf"
    data_dir = Path(_DATA_DIR)
    if not (data_dir / filename).is_file():
        return jsonify({"error": f"Comparison report for '{symbol_a} vs {symbol_b}' not found."}), 404
    return send_from_directory(
        str(data_dir.resolve()), filename,
        as_attachment=True,
    )
