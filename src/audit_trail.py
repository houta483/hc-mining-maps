"""Audit trail CSV generation."""

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def generate_audit_csv(
    mine_area: str,
    intervals: List[Dict],
    output_path: str,
) -> str:
    """Generate audit CSV file with all processed intervals.

    Args:
        mine_area: Mine area name
        intervals: List of interval dictionaries with parsed data
        output_path: Output file path for CSV

    Returns:
        Path to created CSV file
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().isoformat()

    # Define CSV columns
    fieldnames = [
        "mine_area",
        "hole_id",
        "interval_start",
        "interval_end",
        "fm_value",
        "latitude",
        "longitude",
        "box_file_id",
        "box_shared_link",
        "parsed_timestamp",
        "warnings",
    ]

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for interval in intervals:
            writer.writerow(
                {
                    "mine_area": mine_area,
                    "hole_id": interval.get("hole_id", ""),
                    "interval_start": interval.get("start_ft", ""),
                    "interval_end": interval.get("end_ft", ""),
                    "fm_value": interval.get("fm_value", ""),
                    "latitude": interval.get("latitude", ""),
                    "longitude": interval.get("longitude", ""),
                    "box_file_id": interval.get("box_file_id", ""),
                    "box_shared_link": interval.get("box_link", ""),
                    "parsed_timestamp": timestamp,
                    "warnings": "; ".join(interval.get("warnings", [])),
                }
            )

    logger.info(f"Generated audit CSV: {output_file} with {len(intervals)} records")

    return str(output_file)


def cleanup_old_audit_files(logs_dir: str, retention_days: int = 7):
    """Clean up audit CSV files older than retention period.

    Args:
        logs_dir: Directory containing audit files
        retention_days: Number of days to keep files (default: 7)
    """
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0
    deleted_size = 0

    for audit_file in logs_path.glob("audit_*.csv"):
        try:
            # Check file modification time
            file_mtime = datetime.fromtimestamp(audit_file.stat().st_mtime)

            if file_mtime < cutoff_date:
                file_size = audit_file.stat().st_size
                audit_file.unlink()
                deleted_count += 1
                deleted_size += file_size
                logger.debug(
                    f"Deleted old audit file: {audit_file.name} ({file_size} bytes)"
                )
        except Exception as e:
            logger.warning(f"Error deleting audit file {audit_file.name}: {e}")

    if deleted_count > 0:
        logger.info(
            f"Cleaned up {deleted_count} old audit files "
            f"({deleted_size / 1024 / 1024:.2f} MB freed)"
        )
