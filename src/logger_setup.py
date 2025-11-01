"""Logging setup for the pipeline."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record

        Returns:
            JSON string
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class RedactFilter(logging.Filter):
    """Filter that redacts sensitive information from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()

        # Simple redactions: emails, Box share/download URLs, Authorization headers
        try:
            import re

            # redact email addresses
            msg = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "<redacted_email>", msg)

            # redact Box URLs (share/preview/download)
            msg = re.sub(r"https?://(?:[\w.-]*box\.com|[\w.-]*boxcloud\.com)[^\s]*", "<redacted_url>", msg)

            # redact Authorization header values if they sneak into logs
            msg = re.sub(r"(Authorization\s*[:=]\s*)'[^']*'", r"\1'<redacted_token>'", msg)
            msg = re.sub(r"(Authorization\s*[:=]\s*)\"[^\"]*\"", r"\1\"<redacted_token>\"", msg)

            # redact common spreadsheet filenames
            msg = re.sub(r"\b[^\s/]+\.(?:xlsx|xlsm?|csv)\b", "<redacted_file>", msg, flags=re.IGNORECASE)

            # assign redacted message back to record
            record.msg = msg
            record.args = ()
        except Exception:
            # If redaction fails for any reason, pass the record through unchanged
            pass

        return True


def setup_logging(
    log_level: str = "INFO",
    log_path: Optional[str] = None,
    use_json: bool = False,
):
    """Set up logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_path: Optional path to log file
        use_json: Whether to use JSON formatting
    """
    # Convert string level to logging constant
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatters
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RedactFilter())
    root_logger.addHandler(console_handler)

    # File handler if path provided (with rotation)
    if log_path:
        from logging.handlers import RotatingFileHandler

        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Rotate logs: max 10MB per file, keep 5 backup files
        file_handler = RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(RedactFilter())
        root_logger.addHandler(file_handler)

    # Set levels for third-party libraries
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Suppress verbose Box SDK network logging
    logging.getLogger("boxsdk").setLevel(logging.WARNING)
    logging.getLogger("boxsdk.network").setLevel(logging.ERROR)
    logging.getLogger("boxsdk.network.default_network").setLevel(logging.ERROR)
