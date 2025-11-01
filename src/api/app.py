"""Flask REST API application."""

import logging
import os
from flask import Flask
from flask_cors import CORS

from src.api.auth import auth_bp
from src.api.data import data_bp
try:
    from src.api.overlay import overlay_bp
except Exception as exc:  # pragma: no cover - fail open if overlay storage is RO
    overlay_bp = None
    logging.getLogger(__name__).warning(
        "Overlay module disabled: %s", exc
    )
from src.api.database import db

logger = logging.getLogger(__name__)


def create_app():
    """Create and configure Flask app."""
    app = Flask(__name__)

    # Enable CORS for React frontend
    CORS(app, origins=os.environ.get("CORS_ORIGINS", "*").split(","))

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(data_bp)
    if overlay_bp is not None:
        app.register_blueprint(overlay_bp)

    # Initialize database connection on startup
    try:
        db.connect()
        logger.info("Database connection successful")
    except Exception as e:
        msg = f"Database connection failed: {e}, will retry on request"
        logger.warning(msg)

    @app.route("/api/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        db_status = db.test_connection()
        return {
            "status": "ok",
            "database": "connected" if db_status else "disconnected",
        }

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("API_PORT", "5000"))
    host = os.environ.get("API_HOST", "0.0.0.0")
    logger.info(f"Starting Flask API server on {host}:{port}")
    app.run(host=host, port=port, debug=False)
