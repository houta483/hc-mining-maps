#!/bin/bash
# Cleanup old log files to prevent disk space issues

LOGS_DIR="${1:-logs}"
RETENTION_DAYS="${2:-7}"

echo "Cleaning up logs older than $RETENTION_DAYS days in $LOGS_DIR..."

# Find and delete old audit CSV files
find "$LOGS_DIR" -name "audit_*.csv" -type f -mtime +$RETENTION_DAYS -delete

# Clean up old rotated log files
find "$LOGS_DIR" -name "*.log.*" -type f -mtime +30 -delete

# Show current sizes
echo ""
echo "Current log directory size:"
du -sh "$LOGS_DIR" 2>/dev/null || echo "Directory not found"
echo ""
echo "Log files remaining:"
ls -lh "$LOGS_DIR"/*.csv 2>/dev/null | wc -l | xargs echo "  Audit CSVs:"
ls -lh "$LOGS_DIR"/*.log* 2>/dev/null | wc -l | xargs echo "  Log files:"

