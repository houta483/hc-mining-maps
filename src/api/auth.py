"""Authentication endpoints."""

import logging
from flask import Blueprint, request, jsonify
import bcrypt
import jwt
from datetime import datetime, timedelta

from src.api.database import db

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def get_jwt_secret() -> str:
    """Get JWT secret from environment."""
    import os

    secret = os.environ.get("JWT_SECRET_KEY", "")
    if not secret:
        msg = "JWT_SECRET_KEY not set, using default (not secure!)"
        logger.warning(msg)
        return "default-secret-key-change-in-production"
    return secret


def generate_token(user_id: int, username: str) -> str:
    """Generate JWT token for user."""
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(days=7),  # Token expires in 7 days
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, get_jwt_secret(), algorithm="HS256")
    return token


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate user and return JWT token."""
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400

        # Get user from database
        user = db.get_user_by_username(username)
        if not user:
            logger.warning(f"Login attempt with unknown username: {username}")
            return jsonify({"error": "Invalid credentials"}), 401

        # Verify password
        password_hash = user["password_hash"].encode("utf-8")
        password_bytes = password.encode("utf-8")
        if not bcrypt.checkpw(password_bytes, password_hash):
            logger.warning(f"Invalid password for user: {username}")
            return jsonify({"error": "Invalid credentials"}), 401

        # Generate token
        token = generate_token(user["id"], user["username"])

        logger.info(f"Successful login for user: {username}")
        return jsonify(
            {
                "token": token,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                },
            }
        )

    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route("/verify", methods=["GET"])
def verify():
    """Verify token validity."""
    from src.api.middleware import require_auth

    @require_auth
    def verified():
        return jsonify(
            {
                "valid": True,
                "user": {
                    "id": request.user_id,
                    "username": request.username,
                },
            }
        )

    return verified()


@auth_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    db_status = db.test_connection()
    return jsonify(
        {
            "status": "ok",
            "database": "connected" if db_status else "disconnected",
        }
    )
