import gevent_patch  # must be first — patches sockets before any other import  # noqa: F401
import atexit
import logging
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from api.assets   import assets_bp
from api.pipeline import pipeline_bp
from api.reports  import reports_bp
from api.schedule import schedule_bp
from extensions   import limiter

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ENV       = os.getenv("FLASK_ENV", "development")
_IS_PROD   = _ENV == "production"
_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"

if _IS_PROD:
    app = Flask(__name__, static_folder=str(_BUILD_DIR), static_url_path="/")
    logger.info("Production mode — serving React build from %s", _BUILD_DIR)
else:
    app = Flask(__name__)
    CORS(app)
    logger.info("Development mode — CORS enabled, React served by Vite")

limiter.init_app(app)

app.register_blueprint(assets_bp,   url_prefix="/api/assets")
app.register_blueprint(pipeline_bp, url_prefix="/api/pipeline")
app.register_blueprint(reports_bp,  url_prefix="/api/reports")
app.register_blueprint(schedule_bp, url_prefix="/api/schedule")


@app.get("/api/health")
def health():
    from scheduler import _scheduler, start_scheduler
    if not _scheduler.running:
        logger.warning("Health check: scheduler stopped — restarting")
        start_scheduler()
    return jsonify({"status": "ok", "scheduler_running": _scheduler.running})


if _IS_PROD:
    @app.get("/")
    def index():
        return send_from_directory(str(_BUILD_DIR), "index.html")

    @app.errorhandler(404)
    def catch_all(e):
        return send_from_directory(str(_BUILD_DIR), "index.html")


# ── Scheduler lifecycle ───────────────────────────────────────────────────────
from scheduler import start_scheduler, shutdown_scheduler  # noqa: E402
from db import init_db  # noqa: E402

# Call unconditionally at module level so it runs whenever this module is
# imported — which is exactly what Gunicorn does.  start_scheduler() guards
# against double-start internally (if _scheduler.running: return).
with app.app_context():
    init_db()
    start_scheduler()

atexit.register(shutdown_scheduler)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=not _IS_PROD)
