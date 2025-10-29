"""Configuration loader for the pipeline."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class Config:
    """Configuration handler for the pipeline."""

    def __init__(self, config_path: str):
        """Load configuration from YAML file.

        Args:
            config_path: Path to config.yaml file
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_file) as f:
            self.data = yaml.safe_load(f)

        logger.info(f"Loaded configuration from {config_path}")

    def get_mine_areas(self) -> List[Dict]:
        """Get list of mine areas to process.

        Returns:
            List of mine area dictionaries with name and box_folder_id
        """
        return self.data.get("mine_areas", [])

    def get_parent_folder_id(self) -> str:
        """Get parent folder ID for auto-discovery.

        Returns:
            Parent folder ID or empty string if not set
        """
        return self.data.get("parent_folder_id", "")

    def should_auto_discover(self) -> bool:
        """Check if auto-discovery should be used.

        Returns:
            True if mine_areas is empty and parent_folder_id is set
        """
        mine_areas = self.data.get("mine_areas", [])
        parent_folder_id = self.data.get("parent_folder_id", "")
        return not mine_areas and bool(parent_folder_id)

    def get_s3_bucket(self) -> str:
        """Get S3 bucket name."""
        return self.data.get("s3_bucket", "")

    def get_cloudfront_distribution_id(self) -> Optional[str]:
        """Get CloudFront distribution ID."""
        return self.data.get("cloudfront_distribution_id")

    def get_aws_region(self) -> str:
        """Get AWS region."""
        return self.data.get("aws_region", "us-east-1")

    def get_kmz_filename_template(self) -> str:
        """Get KMZ filename template."""
        return self.data.get("kmz_filename_template", "hc_mining_{mine_area}_fm.kmz")

    def get_public_url_template(self) -> str:
        """Get public URL template."""
        return self.data.get(
            "public_url_template", "https://d123456.cloudfront.net/{filename}"
        )

    def get_audit_filename_template(self) -> str:
        """Get audit CSV filename template."""
        return self.data.get(
            "audit_filename_template", "audit_{mine_area}_{timestamp}.csv"
        )

    def get_refresh_seconds(self) -> int:
        """Get refresh interval in seconds."""
        return self.data.get("refresh_seconds", 600)

    def get_box_shared_link_access(self) -> str:
        """Get Box shared link access level."""
        return self.data.get("box_shared_link_access", "collaborators")

    def get_log_level(self) -> str:
        """Get logging level."""
        return self.data.get("log_level", "INFO")

    def get_log_path(self) -> str:
        """Get log file path."""
        return self.data.get("log_path", "/app/logs/pipeline.log")

    def get_max_coordinate_spread_meters(self) -> float:
        """Get maximum coordinate spread in meters."""
        return self.data.get("max_coordinate_spread_meters", 10.0)

    def get_fm_min_value(self) -> float:
        """Get minimum FM value for validation."""
        return self.data.get("fm_min_value", 0.5)

    def get_fm_max_value(self) -> float:
        """Get maximum FM value for validation."""
        return self.data.get("fm_max_value", 7.0)

    def get_audit_retention_days(self) -> int:
        """Get audit file retention period in days."""
        return self.data.get("audit_retention_days", 90)
