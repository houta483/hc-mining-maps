#!/usr/bin/env python3
"""Clean up old audit CSV files from logs directory."""

import sys
from datetime import datetime, timedelta
from pathlib import Path


def cleanup_old_audit_files(logs_dir: str, retention_days: int = 7):
    """Clean up audit CSV files older than retention period."""
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        print(f"Logs directory not found: {logs_dir}")
        return

    cutoff_date = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0
    deleted_size = 0

    print(f"Cleaning up audit files older than {retention_days} days...")
    print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    for audit_file in sorted(logs_path.glob("audit_*.csv")):
        try:
            # Check file modification time
            file_mtime = datetime.fromtimestamp(audit_file.stat().st_mtime)
            file_size = audit_file.stat().st_size

            if file_mtime < cutoff_date:
                audit_file.unlink()
                deleted_count += 1
                deleted_size += file_size
                print(
                    f"  ✓ Deleted: {audit_file.name} ({file_size / 1024:.1f} KB, modified: {file_mtime.strftime('%Y-%m-%d')})"
                )
            else:
                print(
                    f"  - Keeping: {audit_file.name} (modified: {file_mtime.strftime('%Y-%m-%d')})"
                )
        except Exception as e:
            print(f"  ✗ Error deleting {audit_file.name}: {e}")

    print()
    if deleted_count > 0:
        print(
            f"✅ Cleaned up {deleted_count} files ({deleted_size / 1024 / 1024:.2f} MB freed)"
        )
    else:
        print("✅ No old files to clean up")

    # Show remaining size
    remaining_size = sum(f.stat().st_size for f in logs_path.glob("audit_*.csv"))
    remaining_count = len(list(logs_path.glob("audit_*.csv")))
    print(
        f"Remaining: {remaining_count} audit files ({remaining_size / 1024 / 1024:.2f} MB)"
    )


if __name__ == "__main__":
    logs_dir = sys.argv[1] if len(sys.argv) > 1 else "logs"
    retention_days = int(sys.argv[2]) if len(sys.argv) > 2 else 7

    cleanup_old_audit_files(logs_dir, retention_days)
