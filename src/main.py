"""Main orchestrator for the Box to Google Earth pipeline."""

import argparse
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

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


class Pipeline:
    """Main pipeline orchestrator."""

    def __init__(self, config: Config):
        """Initialize pipeline with configuration.

        Args:
            config: Configuration object
        """
        self.config = config

        # Initialize Box client (skip if using local data)
        self.use_local_data = os.environ.get("USE_LOCAL_DATA", "").lower() == "true"
        if not self.use_local_data:
            box_config_path = os.environ.get(
                "BOX_CONFIG", "/app/secrets/box_config.json"
            )
            self.box_client = BoxClient(box_config_path)
        else:
            self.box_client = None
            logger.info("Using local test data mode (USE_LOCAL_DATA=true)")

        # Initialize publisher
        self.publisher = Publisher(
            s3_bucket=config.get_s3_bucket(),
            cloudfront_distribution_id=config.get_cloudfront_distribution_id(),
            aws_region=config.get_aws_region(),
            credentials_file=os.environ.get("AWS_SHARED_CREDENTIALS_FILE"),
        )

        # Metrics
        self.metrics = {
            "files_processed": 0,
            "holes_updated": 0,
            "intervals_added": 0,
            "errors_count": 0,
            "warnings_count": 0,
        }

    def _walk_local_folder_tree(self, mine_area_name: str) -> List[tuple]:
        """Walk local test_data directory instead of Box.

        Args:
            mine_area_name: Name of mine area (e.g., "UP-B")

        Returns:
            List of (hole_folder_name, files) tuples
        """
        results = []
        test_data_dir = Path("/app/test_data") / mine_area_name

        if not test_data_dir.exists():
            logger.warning(f"Local test data not found: {test_data_dir}")
            return results

        logger.info(f"Walking local folder tree from {test_data_dir}")

        for hole_dir in sorted(test_data_dir.iterdir()):
            if hole_dir.is_dir():
                hole_name = hole_dir.name
                hole_files = []

                for file_path in sorted(hole_dir.glob("*.xlsx")):
                    hole_files.append(
                        {
                            "id": f"local_{file_path.stem}",
                            "name": file_path.name,
                            "parent_folder": hole_name,
                            "local_path": str(file_path),
                        }
                    )

                if hole_files:
                    results.append((hole_name, hole_files))

        return results

    def process_mine_area(self, mine_area: Dict) -> Dict[str, List[Dict]]:
        """Process a single mine area.

        Args:
            mine_area: Mine area configuration with name and box_folder_id

        Returns:
            Dictionary mapping hole_id to list of interval data
        """
        mine_area_name = mine_area["name"]
        folder_id = mine_area.get("box_folder_id", "")

        logger.info(f"Processing mine area: {mine_area_name} (folder: {folder_id})")

        # Walk folder tree to get hole folders and files
        if self.use_local_data:
            hole_folders = self._walk_local_folder_tree(mine_area_name)
        else:
            hole_folders = self.box_client.walk_folder_tree(folder_id)

        all_intervals = []
        hole_data: Dict[str, List[Dict]] = {}

        # Create temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Process each hole folder
            for hole_id, files in hole_folders:
                hole_intervals = []

                for file_info in files:
                    file_id = file_info["id"]
                    filename = file_info["name"]

                    try:
                        # Get file path (local or download from Box)
                        if self.use_local_data:
                            local_path = Path(
                                file_info.get("local_path", temp_path / filename)
                            )
                            box_link = ""  # No Box link for local files
                        else:
                            local_path = temp_path / filename
                            self.box_client.download_file(file_id, str(local_path))
                            box_link = self.box_client.ensure_shared_link(
                                file_id, self.config.get_box_shared_link_access()
                            )

                        # Parse file
                        parsed_data = parse_file(str(local_path), hole_id=hole_id)

                        # Validate FM value
                        fm_value = parsed_data["fm_value"]
                        if not (
                            self.config.get_fm_min_value()
                            <= fm_value
                            <= self.config.get_fm_max_value()
                        ):
                            self.metrics["warnings_count"] += 1
                            logger.warning(
                                f"FM value {fm_value} outside expected range "
                                f"({self.config.get_fm_min_value()}-{self.config.get_fm_max_value()}) "
                                f"for {filename}"
                            )

                        # Add Box metadata
                        parsed_data["box_file_id"] = file_id
                        parsed_data["box_link"] = box_link
                        parsed_data["warnings"] = []

                        hole_intervals.append(parsed_data)
                        all_intervals.append(parsed_data)
                        self.metrics["files_processed"] += 1
                        self.metrics["intervals_added"] += 1

                        logger.info(
                            f"Processed {filename}: hole={hole_id}, "
                            f"interval={parsed_data['start_ft']}-{parsed_data['end_ft']}, "
                            f"FM={fm_value:.2f}"
                        )

                    except Exception as e:
                        self.metrics["errors_count"] += 1
                        logger.error(f"Error processing {filename}: {e}", exc_info=True)
                        continue

                if hole_intervals:
                    hole_data[hole_id] = hole_intervals
                    self.metrics["holes_updated"] += 1

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
            self.publisher.upload_kmz(str(output_path), s3_key, public_read=True)

            # Invalidate CloudFront
            self.publisher.invalidate_cloudfront([f"/{kmz_filename}"])

            # Generate public URL
            public_url = self.config.get_public_url_template().format(
                filename=kmz_filename
            )
            logger.info(f"Published KMZ: {public_url}")
            return public_url
        except Exception as e:
            # If upload fails (e.g., no AWS credentials), try Google Drive or nginx
            if "credentials" in str(e).lower() or "NoCredentialsError" in str(
                type(e).__name__
            ):
                logger.warning(f"Skipping S3 upload (no credentials): {e}")

                # External publishing removed - KMZ is now served by backend API
                logger.info(f"KMZ saved locally: {output_path}")
                return str(output_path)
            else:
                # Re-raise other errors
                raise

    def run_once(self) -> int:
        """Run pipeline once for all mine areas.

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        start_time = time.time()

        try:
            # Get mine areas (auto-discover or from config)
            mine_areas = self.config.get_mine_areas()

            # Auto-discover if configured
            if self.config.should_auto_discover():
                if self.use_local_data:
                    # Use local test data discovery
                    test_data_dir = Path("/app/test_data")
                    mine_areas = []
                    if test_data_dir.exists():
                        for area_dir in test_data_dir.iterdir():
                            if area_dir.is_dir():
                                mine_areas.append(
                                    {
                                        "name": area_dir.name,
                                        "box_folder_id": f"local_{area_dir.name}",
                                    }
                                )
                    logger.info(
                        f"Found {len(mine_areas)} mine area(s) in local test_data"
                    )
                else:
                    parent_folder_id = self.config.get_parent_folder_id()
                    logger.info(
                        f"Auto-discovering mine areas from parent folder: {parent_folder_id}"
                    )
                    mine_areas = discover_mine_areas(self.box_client, parent_folder_id)

            if not mine_areas:
                logger.error("No mine areas found or configured")
                return 1

            logger.info(f"Processing {len(mine_areas)} mine area(s)")

            for mine_area in mine_areas:
                try:
                    # Process mine area
                    hole_data = self.process_mine_area(mine_area)

                    if not hole_data:
                        logger.warning(
                            f"No data processed for mine area {mine_area['name']}"
                        )
                        continue

                    # Generate and publish KMZ
                    try:
                        kmz_url = self.generate_and_publish_kmz(mine_area, hole_data)

                        # Publishing to external services removed - KMZ is now served
                        # directly by the backend API at /api/geojson
                        logger.info(
                            f"✅ KMZ generated for {mine_area['name']}. "
                            f"Access via web app at http://localhost:80"
                        )
                    except Exception as e:
                        self.metrics["errors_count"] += 1
                        logger.error(
                            f"Error publishing KMZ for {mine_area['name']}: {e}",
                            exc_info=True,
                        )
                        continue

                except Exception as e:
                    self.metrics["errors_count"] += 1
                    logger.error(
                        f"Error processing mine area {mine_area['name']}: {e}",
                        exc_info=True,
                    )
                    continue

            # Log metrics
            runtime = time.time() - start_time
            self.metrics["runtime_seconds"] = round(runtime, 2)

            logger.info(
                f"Pipeline completed: "
                f"files={self.metrics['files_processed']}, "
                f"holes={self.metrics['holes_updated']}, "
                f"intervals={self.metrics['intervals_added']}, "
                f"errors={self.metrics['errors_count']}, "
                f"warnings={self.metrics['warnings_count']}, "
                f"runtime={runtime:.1f}s"
            )

            # Return non-zero exit code if errors occurred
            if self.metrics["errors_count"] > 0:
                return 1

            return 0

        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return 1

    def run_continuous(self):
        """Run pipeline continuously on configured interval."""
        refresh_seconds = self.config.get_refresh_seconds()

        logger.info(
            f"Starting continuous pipeline (refresh interval: {refresh_seconds}s)"
        )

        while True:
            try:
                exit_code = self.run_once()
                if exit_code != 0:
                    logger.error(f"Pipeline run failed with exit code {exit_code}")

                logger.info(f"Waiting {refresh_seconds}s before next run...")
                time.sleep(refresh_seconds)

            except KeyboardInterrupt:
                logger.info("Pipeline stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in continuous mode: {e}", exc_info=True)
                time.sleep(refresh_seconds)


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
