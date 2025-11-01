"""Main orchestrator for the Box to Google Earth pipeline."""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Setup debugger if DEBUG_MODE is enabled
if os.environ.get("DEBUG_MODE", "").lower() == "true":
    try:
        import debugpy

        debugpy.listen(("0.0.0.0", 5680))
        print("🐛 Debugger listening on port 5680")
        # Wait for debugger to attach before starting execution
        print("⏳ Waiting for debugger to attach...")
        debugpy.wait_for_client()
        print("✅ Debugger attached! Starting execution...")
    except ImportError:
        print("⚠️  debugpy not installed. Install with: pip install debugpy")

from src.audit_trail import generate_audit_csv, cleanup_old_audit_files
from src.box_auto_discover import discover_mine_areas
from src.box_client import BoxClient
from src.config_loader import Config
from src.interval_parser import parse_file
from src.kml_builder import build_kmz
from src.logger_setup import setup_logging
from src.publisher import Publisher

logger = logging.getLogger(__name__)

STATUS_FILE_ENV_VAR = "PIPELINE_STATUS_PATH"
STATUS_FILE_DEFAULT = "/app/logs/pipeline_status.json"
TRIGGER_FILE_ENV_VAR = "PIPELINE_TRIGGER_PATH"
TRIGGER_FILE_DEFAULT = "/app/logs/manual_trigger.json"


class Pipeline:
    """Main pipeline orchestrator."""

    def __init__(self, config: Config):
        """Initialize pipeline with configuration.

        Args:
            config: Configuration object
        """
        self.config = config

        # Initialize Box client
        box_config_path = os.environ.get(
            "BOX_CONFIG",
            "/app/secrets/box_config.json",
        )
        self.box_client = BoxClient(box_config_path)

        # Initialize publisher
        self.publisher = Publisher(
            s3_bucket=config.get_s3_bucket(),
            cloudfront_distribution_id=config.get_cloudfront_distribution_id(),
            aws_region=config.get_aws_region(),
            credentials_file=os.environ.get("AWS_SHARED_CREDENTIALS_FILE"),
        )

        # Paths for status tracking and manual triggers
        self.status_path = Path(
            os.environ.get(STATUS_FILE_ENV_VAR, STATUS_FILE_DEFAULT)
        )
        self.manual_trigger_path = Path(
            os.environ.get(TRIGGER_FILE_ENV_VAR, TRIGGER_FILE_DEFAULT)
        )

        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.manual_trigger_path.parent.mkdir(parents=True, exist_ok=True)

        self._reset_metrics()
        self._write_status(
            {
                "state": "idle",
                "message": "Pipeline initialized",
                "last_run_status": None,
            }
        )

    def _reset_metrics(self) -> None:
        """Reset metric counters for a new run."""

        self.metrics = {
            "files_processed": 0,
            "holes_updated": 0,
            "intervals_added": 0,
            "errors_count": 0,
            "warnings_count": 0,
        }

    def _write_status(self, updates: Dict) -> None:
        """Persist pipeline status to disk for the API/frontend."""

        status: Dict = {}
        if self.status_path.exists():
            try:
                status = json.loads(self.status_path.read_text())
            except Exception as exc:  # pragma: no cover - best effort logging
                logger.warning("Could not read existing status file: %s", exc)
                status = {}

        status.update(updates)
        status["updated_at"] = datetime.utcnow().isoformat() + "Z"

        tmp_path = self.status_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(status, indent=2))
            tmp_path.replace(self.status_path)
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.error("Failed to write pipeline status: %s", exc)

    def _consume_manual_trigger(self) -> Optional[Dict]:
        """Return manual trigger metadata if requested, clearing the flag."""

        if not self.manual_trigger_path.exists():
            return None

        trigger_data: Dict = {}
        try:
            trigger_text = self.manual_trigger_path.read_text()
            if trigger_text:
                trigger_data = json.loads(trigger_text)
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.warning("Failed to parse manual trigger file: %s", exc)
            trigger_data = {"source": "manual"}

        try:
            self.manual_trigger_path.unlink()
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.warning("Failed to remove manual trigger file: %s", exc)

        trigger_data.setdefault("source", "manual")
        return trigger_data

    def process_mine_area(self, mine_area: Dict) -> Dict[str, List[Dict]]:
        """Process a single mine area.

        Args:
            mine_area: Mine area configuration with name and box_folder_id

        Returns:
            Dictionary mapping hole_id to list of interval data
        """
        mine_area_name = mine_area["name"]
        folder_id = mine_area.get("box_folder_id", "")

        logger.info(
            "Processing mine area: %s (folder: %s)",
            mine_area_name,
            folder_id,
        )

        # Walk folder tree to get hole folders and files
        hole_folders = self.box_client.walk_folder_tree(folder_id)

        all_intervals = []
        hole_data: Dict[str, List[Dict]] = {}
        processed_holes: set[str] = set()
        metrics = self.metrics

        # Create temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Process each hole folder
            for folder_hole_id, files in hole_folders:
                for file_info in files:
                    file_id = file_info["id"]
                    filename = file_info["name"]

                    try:
                        # Download file from Box
                        local_path = temp_path / filename
                        self.box_client.download_file(file_id, str(local_path))
                        box_link = self.box_client.get_file_link(
                            file_id, self.config.get_box_shared_link_access()
                        )

                        # Parse file
                        parsed_data = parse_file(
                            str(local_path),
                            hole_id=folder_hole_id,
                        )

                        target_id = parsed_data.get(
                            "hole_id",
                            folder_hole_id,
                        )
                        file_warnings = parsed_data.setdefault("warnings", [])

                        if target_id != folder_hole_id:
                            mismatch_msg = (
                                "{file}: sheet hole '{sheet}' != " "folder '{folder}'"
                            ).format(
                                file=filename,
                                sheet=target_id,
                                folder=folder_hole_id,
                            )
                            file_warnings.append(mismatch_msg)

                        fm_value = parsed_data["fm_value"]
                        fm_min = self.config.get_fm_min_value()
                        fm_max = self.config.get_fm_max_value()
                        if not (fm_min <= fm_value <= fm_max):
                            fm_warning = (
                                "{file}: FM {value} outside range " "{lower}-{upper}"
                            ).format(
                                file=filename,
                                value=fm_value,
                                lower=fm_min,
                                upper=fm_max,
                            )
                            file_warnings.append(fm_warning)

                        if file_warnings:
                            for warning_msg in file_warnings:
                                logger.warning(warning_msg)
                            metrics["warnings_count"] += len(file_warnings)

                        # Add Box metadata
                        parsed_data["box_file_id"] = file_id
                        parsed_data["box_link"] = box_link

                        hole_data.setdefault(
                            target_id,
                            [],
                        ).append(parsed_data)
                        all_intervals.append(parsed_data)
                        metrics["files_processed"] += 1
                        metrics["intervals_added"] += 1
                        if target_id not in processed_holes:
                            processed_holes.add(target_id)
                            metrics["holes_updated"] += 1

                        logger.info(
                            "Processed %s: hole=%s, interval=%s-%s, FM=%.2f",
                            filename,
                            target_id,
                            parsed_data["start_ft"],
                            parsed_data["end_ft"],
                            fm_value,
                        )

                    except Exception as e:
                        metrics["errors_count"] += 1
                        logger.error(
                            "Error processing %s: %s",
                            filename,
                            e,
                            exc_info=True,
                        )
                        continue

        # Generate audit CSV
        if all_intervals:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            audit_filename = self.config.get_audit_filename_template().format(
                mine_area=mine_area_name, timestamp=timestamp
            )
            audit_path = Path("/app/logs") / audit_filename
            generate_audit_csv(mine_area_name, all_intervals, str(audit_path))

            # Clean up old audit files (keep last 7 days by default)
            retention_days = self.config.get_audit_retention_days()
            cleanup_old_audit_files("/app/logs", retention_days)

            # Upload audit CSV to S3
            try:
                s3_key = f"audits/{audit_filename}"
                self.publisher.upload_audit_csv(str(audit_path), s3_key)
            except Exception as e:
                logger.warning(f"Failed to upload audit CSV: {e}")

        return hole_data

    def generate_and_publish_kmz(
        self, mine_area: Dict, hole_data: Dict[str, List[Dict]]
    ) -> str:
        """Generate KMZ and publish to S3/CloudFront.

        Args:
            mine_area: Mine area configuration
            hole_data: Dictionary mapping hole_id to intervals

        Returns:
            Public URL of published KMZ
        """
        mine_area_name = mine_area["name"]

        # Generate KMZ filename
        kmz_filename = self.config.get_kmz_filename_template().format(
            mine_area=mine_area_name
        )

        # Build KMZ
        output_path = Path("/app/output") / kmz_filename
        build_kmz(
            mine_area_name,
            hole_data,
            str(output_path),
            max_spread_meters=self.config.get_max_coordinate_spread_meters(),
        )

        # Upload to S3 (optional - skip if no credentials)
        try:
            s3_key = kmz_filename
            self.publisher.upload_kmz(
                str(output_path),
                s3_key,
                public_read=True,
            )

            # Invalidate CloudFront
            self.publisher.invalidate_cloudfront([f"/{kmz_filename}"])

            # Generate public URL
            public_url = self.config.get_public_url_template().format(
                filename=kmz_filename
            )
            logger.info(f"Published KMZ: {public_url}")
            return public_url
        except Exception as e:
            # If upload fails (e.g., missing AWS creds)
            # fall back to the local file
            if "credentials" in str(e).lower() or "NoCredentialsError" in str(
                type(e).__name__
            ):
                logger.warning("Skipping S3 upload (no credentials): %s", e)

                # External publishing is handled by the backend API
                logger.info("KMZ saved locally: %s", output_path)
                return str(output_path)
            else:
                # Re-raise other errors
                raise

    def run_once(self, trigger: Optional[Dict] = None) -> int:
        """Run pipeline once for all mine areas.

        Args:
            trigger: Metadata about what initiated the run.

        Returns:
            Exit code (0 for success, non-zero for failure)
        """

        trigger_data = trigger or {"source": "schedule"}
        start_time = time.time()
        run_started_at = datetime.utcnow().isoformat() + "Z"

        self._reset_metrics()

        trigger_source = trigger_data.get("source", "schedule")
        logger.info(
            "Starting pipeline run (trigger=%s, requested_by=%s)",
            trigger_source,
            trigger_data.get("requested_by", "system"),
        )

        self._write_status(
            {
                "state": "running",
                "message": "Pipeline run started",
                "last_run_started": run_started_at,
                "last_run_completed": None,
                "last_run_status": "running",
                "trigger": trigger_data,
                "metrics": self.metrics,
            }
        )

        exit_code = 1
        status_message = "Pipeline failed"

        try:
            # Get mine areas (auto-discover or from config)
            mine_areas = self.config.get_mine_areas()

            # Auto-discover if configured
            if self.config.should_auto_discover():
                parent_folder_id = self.config.get_parent_folder_id()
                logger.info(
                    "Auto-discovering mine areas from parent folder: %s",
                    parent_folder_id,
                )
                mine_areas = discover_mine_areas(
                    self.box_client,
                    parent_folder_id,
                )

            if not mine_areas:
                logger.error("No mine areas found or configured")
                status_message = "No mine areas found or configured"
                exit_code = 1
            else:
                logger.info("Processing %d mine area(s)", len(mine_areas))

                for mine_area in mine_areas:
                    try:
                        # Process mine area
                        hole_data = self.process_mine_area(mine_area)

                        if not hole_data:
                            logger.warning(
                                "No data processed for mine area %s",
                                mine_area["name"],
                            )
                            continue

                        # Generate and publish KMZ
                        try:
                            self.generate_and_publish_kmz(mine_area, hole_data)

                            # Frontend fetches the KMZ via the backend API
                            logger.info(
                                "✅ KMZ generated for %s. "
                                "Access via web app at http://localhost:80",
                                mine_area["name"],
                            )
                        except Exception as exc:
                            self.metrics["errors_count"] += 1
                            logger.error(
                                "Error publishing KMZ for %s: %s",
                                mine_area["name"],
                                exc,
                                exc_info=True,
                            )
                            continue

                    # pragma: no cover - guardrail
                    except Exception as exc:
                        self.metrics["errors_count"] += 1
                        logger.error(
                            "Error processing mine area %s: %s",
                            mine_area["name"],
                            exc,
                            exc_info=True,
                        )
                        continue

                runtime = time.time() - start_time
                self.metrics["runtime_seconds"] = round(runtime, 2)

                logger.info(
                    "Pipeline completed: files=%s, holes=%s, intervals=%s, "
                    "errors=%s, warnings=%s, runtime=%.1fs",
                    self.metrics["files_processed"],
                    self.metrics["holes_updated"],
                    self.metrics["intervals_added"],
                    self.metrics["errors_count"],
                    self.metrics["warnings_count"],
                    runtime,
                )

                # Treat runs with at least some intervals as successful,
                # even if some files failed, so the UI can update.
                if self.metrics["intervals_added"] > 0:
                    if self.metrics["errors_count"] > 0:
                        exit_code = 0
                        status_message = "Pipeline completed with some errors"
                    else:
                        exit_code = 0
                        status_message = "Pipeline run completed successfully"
                else:
                    exit_code = 1
                    status_message = "Pipeline completed with no intervals processed"

        # pragma: no cover - operational guardrail
        except Exception as exc:
            logger.error("Pipeline failed: %s", exc, exc_info=True)
            status_message = f"Pipeline failed: {exc}"
            exit_code = 1
        finally:
            runtime = time.time() - start_time
            runtime_sec = round(runtime, 2)
            self.metrics.setdefault(
                "runtime_seconds",
                runtime_sec,
            )

            completed_at = datetime.utcnow().isoformat() + "Z"
            final_status = {
                "state": "idle",
                "message": status_message,
                "last_run_started": run_started_at,
                "last_run_completed": completed_at,
                "last_run_status": "success" if exit_code == 0 else "error",
                "trigger": trigger_data,
                "metrics": self.metrics,
                "exit_code": exit_code,
            }
            self._write_status(final_status)

        return exit_code

    def run_continuous(self):
        """Run pipeline continuously on configured interval."""
        refresh_seconds = self.config.get_refresh_seconds()

        logger.info(
            "Starting continuous pipeline (refresh interval: %ss)",
            refresh_seconds,
        )

        if refresh_seconds > 0:
            check_interval = max(1, min(10, int(refresh_seconds)))
        else:
            check_interval = 5

        while True:
            try:
                trigger_data = self._consume_manual_trigger()
                if trigger_data:
                    logger.info(
                        "Manual pipeline run requested by %s",
                        trigger_data.get("requested_by", "unknown"),
                    )
                else:
                    trigger_data = {"source": "schedule"}

                exit_code = self.run_once(trigger_data)
                if exit_code != 0:
                    logger.error(
                        "Pipeline run failed with exit code %s",
                        exit_code,
                    )

                if refresh_seconds <= 0:
                    continue

                logger.info(
                    "Waiting %ss before next scheduled run...",
                    refresh_seconds,
                )

                wait_elapsed = 0.0
                while wait_elapsed < refresh_seconds:
                    sleep_for = min(
                        check_interval,
                        refresh_seconds - wait_elapsed,
                    )
                    time.sleep(sleep_for)
                    wait_elapsed += sleep_for

                    trigger_data = self._consume_manual_trigger()
                    if trigger_data:
                        logger.info(
                            "Manual pipeline run requested by %s",
                            trigger_data.get("requested_by", "unknown"),
                        )
                        exit_code = self.run_once(trigger_data)
                        if exit_code != 0:
                            logger.error(
                                "Pipeline run failed with exit code %s",
                                exit_code,
                            )
                        wait_elapsed = 0.0
                        logger.info(
                            "Waiting %ss before next scheduled run...",
                            refresh_seconds,
                        )

            except KeyboardInterrupt:
                logger.info("Pipeline stopped by user")
                break
            # pragma: no cover - operational guardrail
            except Exception as exc:
                logger.error(
                    "Unexpected error in continuous mode: %s",
                    exc,
                    exc_info=True,
                )
                time.sleep(max(refresh_seconds, check_interval))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Box to Google Earth Borehole Analysis Pipeline"
    )
    parser.add_argument(
        "--config",
        default="/app/config/config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (default: continuous mode)",
    )
    parser.add_argument(
        "--web-server",
        action="store_true",
        help="Start web server for Mapbox visualization",
    )
    parser.add_argument(
        "--log-level",
        help="Override log level from config",
    )
    parser.add_argument(
        "--log-path",
        help="Override log path from config",
    )

    args = parser.parse_args()

    # Load configuration
    config = Config(args.config)

    # Set up logging
    log_level = args.log_level or config.get_log_level()
    log_path = args.log_path or config.get_log_path()
    setup_logging(log_level=log_level, log_path=log_path, use_json=False)

    # Initialize pipeline
    pipeline = Pipeline(config)

    # Pipeline service - background processing only
    # Web server is now a separate service in docker-compose
    if args.once:
        exit_code = pipeline.run_once()
        sys.exit(exit_code)
    else:
        pipeline.run_continuous()


if __name__ == "__main__":
    main()
