"""
Shared progress-emission helpers for pipeline and comparison WebSocket runs.
Both pipeline and comparison socket handlers import emit_progress from here.
"""
import logging
from app import socketio  # works because app.py defines socketio before importing socket_handlers

PIPELINE_STAGES = [
    ("init",     "Initialising",          0),
    ("fetch",    "Fetching market data",  15),
    ("clean",    "Cleaning data",         30),
    ("store",    "Storing to database",   42),
    ("analyse",  "Running analysis",      55),
    ("charts",   "Generating charts",     70),
    ("report",   "Building PDF report",   85),
    ("complete", "Complete",             100),
]

COMPARISON_STAGES = [
    ("init",     "Initialising",                 0),
    ("fetch_a",  "Fetching data for asset A",    10),
    ("fetch_b",  "Fetching data for asset B",    22),
    ("store",    "Storing to database",          34),
    ("analyse",  "Running comparison analysis",  46),
    ("charts",   "Generating comparison charts", 62),
    ("report",   "Building combined PDF",        78),
    ("complete", "Complete",                    100),
]


def emit_progress(run_id: str, stage: str, message: str, percent: int, error=None):
    payload = {
        "run_id":  run_id,
        "stage":   stage,
        "message": message,
        "percent": percent,
        "error":   error,
    }
    socketio.emit("pipeline_progress", payload, room=run_id)
    logging.info("[WS] run_id=%s stage=%s percent=%d%% msg=%s", run_id, stage, percent, message)
