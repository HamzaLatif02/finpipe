import logging
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from api.assets import assets_bp
from api.pipeline import pipeline_bp
from api.reports import reports_bp

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ENV        = os.getenv("FLASK_ENV", "development")
_IS_PROD    = _ENV == "production"
_BUILD_DIR  = Path(__file__).parent.parent / "frontend" / "build"

# In production Flask serves the React build; in development the Vite dev
# server runs separately and proxies /api requests to Flask.
if _IS_PROD:
    app = Flask(__name__, static_folder=str(_BUILD_DIR), static_url_path="/")
    logger.info("Production mode — serving React build from %s", _BUILD_DIR)
else:
    app = Flask(__name__)
    CORS(app)  # allow all origins so the Vite dev server can call the API
    logger.info("Development mode — CORS enabled, React served by Vite")

app.register_blueprint(assets_bp, url_prefix="/api/assets")
app.register_blueprint(pipeline_bp, url_prefix="/api/pipeline")
app.register_blueprint(reports_bp, url_prefix="/api/reports")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


if _IS_PROD:
    @app.get("/")
    def index():
        return send_from_directory(str(_BUILD_DIR), "index.html")

    @app.errorhandler(404)
    def catch_all(e):
        # Let React Router handle any path that isn't an /api route.
        return send_from_directory(str(_BUILD_DIR), "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=not _IS_PROD)
