import sys
import os
import logging

from flask import jsonify, request
from flask_smorest import Blueprint

# explorer.py lives in the project root, one level above backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from explorer import ASSET_CATEGORIES, PERIODS, INTERVALS, validate_ticker
from extensions import limiter
from schemas import (
    CategoriesResponseSchema, PeriodsResponseSchema,
    IntervalsResponseSchema, ValidateResponseSchema, ErrorResponseSchema,
)

assets_bp = Blueprint(
    "Assets", __name__,
    description="Asset categories, available periods/intervals, and ticker validation.",
)
logger = logging.getLogger(__name__)


@assets_bp.get("/categories")
@assets_bp.response(200, CategoriesResponseSchema())
@assets_bp.alt_response(500, schema=ErrorResponseSchema())
@limiter.exempt
def get_categories():
    """Return all supported asset categories with example tickers."""
    try:
        categories = {
            category: {
                "description": data["description"],
                "examples": [
                    {"symbol": symbol, "name": name}
                    for symbol, name in data["examples"]
                ],
            }
            for category, data in ASSET_CATEGORIES.items()
        }
        return jsonify({"categories": categories})
    except Exception as exc:
        logger.exception("Failed to fetch categories")
        return jsonify({"error": str(exc)}), 500


@assets_bp.get("/periods")
@assets_bp.response(200, PeriodsResponseSchema())
@assets_bp.alt_response(500, schema=ErrorResponseSchema())
@limiter.exempt
def get_periods():
    """Return all supported analysis periods (e.g. 1y, 2y, 5y, custom)."""
    try:
        periods = [{"value": value, "label": label} for value, label in PERIODS]
        return jsonify({"periods": periods})
    except Exception as exc:
        logger.exception("Failed to fetch periods")
        return jsonify({"error": str(exc)}), 500


@assets_bp.get("/intervals")
@assets_bp.response(200, IntervalsResponseSchema())
@assets_bp.alt_response(500, schema=ErrorResponseSchema())
@limiter.exempt
def get_intervals():
    """Return all supported data intervals (daily, weekly, monthly)."""
    try:
        intervals = [{"value": value, "label": label} for value, label in INTERVALS]
        return jsonify({"intervals": intervals})
    except Exception as exc:
        logger.exception("Failed to fetch intervals")
        return jsonify({"error": str(exc)}), 500


@assets_bp.get("/validate")
@assets_bp.response(200, ValidateResponseSchema())
@assets_bp.alt_response(400, schema=ErrorResponseSchema())
@assets_bp.alt_response(500, schema=ErrorResponseSchema())
@limiter.exempt
def validate():
    """Validate a ticker symbol against Yahoo Finance.

    Query parameter: `symbol` (required) — e.g. `AAPL`, `BTC-USD`, `^GSPC`
    """
    symbol = request.args.get("symbol", "").strip()
    if not symbol:
        return jsonify({"error": "symbol query parameter is required"}), 400

    try:
        info = validate_ticker(symbol.upper())
        if info:
            return jsonify({"valid": True, "info": info})
        return jsonify({"valid": False, "error": f"'{symbol}' could not be found on Yahoo Finance"})
    except Exception as exc:
        logger.exception("Failed to validate ticker %s", symbol)
        return jsonify({"error": str(exc)}), 500
