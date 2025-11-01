"""JWT authentication middleware."""

import logging
from functools import wraps
from flask import request, jsonify
import jwt

logger = logging.getLogger(__name__)


def get_jwt_secret() -> str:
    """Get JWT secret from environment."""
    import os

    secret = os.environ.get("JWT_SECRET_KEY", "")
    if not secret:
        msg = "JWT_SECRET_KEY not set, using default (not secure!)"
        logger.warning(msg)
        return "default-secret-key-change-in-production"
    return secret


def verify_token(token: str) -> dict:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


def require_auth(f):
    """Decorator to require JWT authentication."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header:
            try:
                token = auth_header.split(" ")[1]  # "Bearer <token>"
            except IndexError:
                return jsonify({"error": "Invalid authorization header"}), 401

        if not token:
            query_token = request.args.get("token", "").strip()
            if query_token.lower().startswith("bearer "):
                query_token = query_token.split(" ", 1)[1]
            token = query_token or None

        if not token:
            return jsonify({"error": "Missing authorization token"}), 401

        # Verify token
        payload = verify_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Add user info to request context
        request.user_id = payload.get("user_id")
        request.username = payload.get("username")

        return f(*args, **kwargs)

    return decorated_function
