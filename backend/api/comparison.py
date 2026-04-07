import logging
import os
import sys
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from comparison_analysis import run_comparison           # noqa: E402
from comparison_charts   import generate_comparison_charts  # noqa: E402
from comparison_report   import generate_comparison_report  # noqa: E402
from fetcher import fetch_data                           # noqa: E402
from cleaner import clean_data                           # noqa: E402
from db      import insert_prices, insert_info, init_db  # noqa: E402
from extensions import limiter                           # noqa: E402

comparison_bp = Blueprint("comparison", __name__)
logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(_ROOT, "data")

_REQUIRED_CONFIG = {"symbol", "name", "asset_type", "currency", "period", "interval"}


@comparison_bp.post("/run")
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

    # Strip non-serialisable analysis objects (DataFrames) from the response
    comparison_safe = {
        k: v for k, v in comparison.items()
        if k not in ("analysis_a", "analysis_b")
    }

    return jsonify({
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
        "pdf_url":      f"/api/comparison/pdf/{sym_a}/{sym_b}",
    })


@comparison_bp.get("/pdf/<symbol_a>/<symbol_b>")
def view_pdf(symbol_a: str, symbol_b: str):
    filename = f"{symbol_a}_vs_{symbol_b}_comparison_report.pdf"
    data_dir = Path(_DATA_DIR)
    if not (data_dir / filename).is_file():
        return jsonify({"error": f"Comparison report for '{symbol_a} vs {symbol_b}' not found."}), 404
    return send_from_directory(
        str(data_dir.resolve()), filename,
        mimetype="application/pdf", as_attachment=False,
    )


@comparison_bp.get("/download/<symbol_a>/<symbol_b>")
def download_pdf(symbol_a: str, symbol_b: str):
    filename = f"{symbol_a}_vs_{symbol_b}_comparison_report.pdf"
    data_dir = Path(_DATA_DIR)
    if not (data_dir / filename).is_file():
        return jsonify({"error": f"Comparison report for '{symbol_a} vs {symbol_b}' not found."}), 404
    return send_from_directory(
        str(data_dir.resolve()), filename,
        as_attachment=True,
    )
