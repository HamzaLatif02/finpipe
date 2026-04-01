import sys
import os
import logging

from flask import Blueprint, jsonify, request

# explorer.py lives in the project root, one level above backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from explorer import ASSET_CATEGORIES, PERIODS, INTERVALS, validate_ticker

assets_bp = Blueprint("assets", __name__)
logger = logging.getLogger(__name__)


@assets_bp.get("/categories")
def get_categories():
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
def get_periods():
    try:
        periods = [{"value": value, "label": label} for value, label in PERIODS]
        return jsonify({"periods": periods})
    except Exception as exc:
        logger.exception("Failed to fetch periods")
        return jsonify({"error": str(exc)}), 500


@assets_bp.get("/intervals")
def get_intervals():
    try:
        intervals = [{"value": value, "label": label} for value, label in INTERVALS]
        return jsonify({"intervals": intervals})
    except Exception as exc:
        logger.exception("Failed to fetch intervals")
        return jsonify({"error": str(exc)}), 500


@assets_bp.get("/validate")
def validate():
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
