import logging
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from api.assets import assets_bp
from api.pipeline import pipeline_bp
from api.reports import reports_bp

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # allow all origins in development

app.register_blueprint(assets_bp, url_prefix="/api/assets")
app.register_blueprint(pipeline_bp, url_prefix="/api/pipeline")
app.register_blueprint(reports_bp, url_prefix="/api/reports")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
