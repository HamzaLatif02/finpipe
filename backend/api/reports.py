import logging
import os
import sys
from pathlib import Path

from flask import Blueprint, jsonify, send_from_directory

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _ROOT)

_CHARTS_DIR = os.path.join(_ROOT, "data", "charts")
_DATA_DIR   = os.path.join(_ROOT, "data")

reports_bp = Blueprint("reports", __name__)
logger = logging.getLogger(__name__)


@reports_bp.get("/charts/<filename>")
def serve_chart(filename: str):
    charts_dir = Path(_CHARTS_DIR)
    if not (charts_dir / filename).is_file():
        return jsonify({"error": f"Chart '{filename}' not found"}), 404
    return send_from_directory(str(charts_dir.resolve()), filename)


@reports_bp.get("/pdf/<symbol>")
def serve_pdf(symbol: str):
    filename = f"{symbol}_report.pdf"
    data_dir = Path(_DATA_DIR)
    if not (data_dir / filename).is_file():
        return jsonify({"error": f"PDF report for '{symbol}' not found"}), 404
    return send_from_directory(str(data_dir.resolve()), filename, as_attachment=True)


@reports_bp.get("/list/<symbol>")
def list_reports(symbol: str):
    try:
        charts_dir = Path(_CHARTS_DIR)
        if charts_dir.is_dir():
            charts = sorted(
                f.name
                for f in charts_dir.iterdir()
                if f.is_file() and f.name.startswith(f"{symbol}_") and f.suffix == ".png"
            )
        else:
            charts = []

        pdf_path = Path(_DATA_DIR) / f"{symbol}_report.pdf"
        has_pdf = pdf_path.is_file()

        return jsonify({"symbol": symbol, "charts": charts, "has_pdf": has_pdf})
    except Exception as exc:
        logger.exception("list_reports failed for %s", symbol)
        return jsonify({"error": str(exc)}), 500
