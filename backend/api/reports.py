import logging
import os
import sys
from pathlib import Path

from flask import jsonify, send_from_directory
from flask_smorest import Blueprint

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _ROOT)

_CHARTS_DIR = os.path.join(_ROOT, "data", "charts")
_DATA_DIR   = os.path.join(_ROOT, "data")

from schemas import ReportListResponseSchema, ErrorResponseSchema  # noqa: E402

reports_bp = Blueprint(
    "Reports", __name__,
    description="Serve generated chart images and PDF reports.",
)
logger = logging.getLogger(__name__)


@reports_bp.get("/charts/<filename>")
@reports_bp.alt_response(404, schema=ErrorResponseSchema())
def serve_chart(filename: str):
    """Serve a chart PNG by filename (as returned in `chart_urls`)."""
    charts_dir = Path(_CHARTS_DIR)
    if not (charts_dir / filename).is_file():
        return jsonify({"error": f"Chart '{filename}' not found"}), 404
    return send_from_directory(str(charts_dir.resolve()), filename)


@reports_bp.get("/pdf/<symbol>")
@reports_bp.alt_response(404, schema=ErrorResponseSchema())
def serve_pdf(symbol: str):
    """Download the PDF report for a symbol as an attachment."""
    filename = f"{symbol}_report.pdf"
    data_dir = Path(_DATA_DIR)
    if not (data_dir / filename).is_file():
        return jsonify({"error": f"PDF report for '{symbol}' not found"}), 404
    return send_from_directory(str(data_dir.resolve()), filename, as_attachment=True)


@reports_bp.get("/view/<symbol>")
@reports_bp.alt_response(404, schema=ErrorResponseSchema())
def view_report(symbol: str):
    """Serve the PDF report for a symbol inline in the browser."""
    filename = f"{symbol}_report.pdf"
    data_dir = Path(_DATA_DIR)
    if not (data_dir / filename).is_file():
        return jsonify({"error": f"PDF report for '{symbol}' not found"}), 404
    return send_from_directory(
        str(data_dir.resolve()), filename,
        mimetype="application/pdf", as_attachment=False,
    )


@reports_bp.get("/list/<symbol>")
@reports_bp.response(200, ReportListResponseSchema())
@reports_bp.alt_response(500, schema=ErrorResponseSchema())
def list_reports(symbol: str):
    """List available chart files and whether a PDF exists for a symbol."""
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
