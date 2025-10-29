"""Publisher for uploading KMZ files to S3 and invalidating CloudFront."""

import logging
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class Publisher:
    """Publisher for S3 uploads and CloudFront invalidation."""

    def __init__(
        self,
        s3_bucket: str,
        cloudfront_distribution_id: Optional[str] = None,
        aws_region: str = "us-east-1",
        credentials_file: Optional[str] = None,
    ):
        """Initialize publisher with AWS configuration.

        Args:
            s3_bucket: S3 bucket name
            cloudfront_distribution_id: CloudFront distribution ID (optional)
            aws_region: AWS region
            credentials_file: Path to AWS credentials file (optional)
        """
        self.s3_bucket = s3_bucket
        self.cloudfront_distribution_id = cloudfront_distribution_id
        self.aws_region = aws_region

        # Initialize AWS clients
        try:
            if credentials_file:
                session = boto3.Session(
                    profile_name=None,  # Use default profile
                )
                self.s3_client = session.client("s3", region_name=aws_region)
                if cloudfront_distribution_id:
                    self.cloudfront_client = session.client(
                        "cloudfront", region_name=aws_region
                    )
                else:
                    self.cloudfront_client = None
            else:
                # Use default credentials (IAM role, env vars, etc.)
                self.s3_client = boto3.client("s3", region_name=aws_region)
                if cloudfront_distribution_id:
                    self.cloudfront_client = boto3.client(
                        "cloudfront", region_name=aws_region
                    )
                else:
                    self.cloudfront_client = None

            logger.info(
                f"Publisher initialized: bucket={s3_bucket}, region={aws_region}"
            )
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise

    def upload_kmz(
        self, local_path: str, s3_key: str, public_read: bool = False
    ) -> str:
        """Upload KMZ file to S3.

        Args:
            local_path: Local file path
            s3_key: S3 object key
            public_read: Whether to make object publicly readable

        Returns:
            S3 URL of uploaded file

        Raises:
            ClientError: If upload fails
        """
        try:
            local_file = Path(local_path)
            if not local_file.exists():
                raise FileNotFoundError(f"File not found: {local_path}")

            # Determine content type
            content_type = "application/vnd.google-earth.kmz"

            # ACL setting
            extra_args = {"ContentType": content_type}
            if public_read:
                extra_args["ACL"] = "public-read"

            # Upload file
            self.s3_client.upload_file(
                str(local_file),
                self.s3_bucket,
                s3_key,
                ExtraArgs=extra_args,
            )

            s3_url = (
                f"https://{self.s3_bucket}.s3.{self.aws_region}.amazonaws.com/{s3_key}"
            )

            logger.info(f"Uploaded KMZ to S3: {s3_url}")
            return s3_url

        except ClientError as e:
            logger.error(f"Error uploading to S3: {e}")
            raise

    def invalidate_cloudfront(self, paths: list[str]) -> Optional[str]:
        """Create CloudFront invalidation.

        Args:
            paths: List of paths to invalidate (e.g., ["/hc_mining_UP-B_fm.kmz"])

        Returns:
            Invalidation ID or None if CloudFront not configured
        """
        if not self.cloudfront_client or not self.cloudfront_distribution_id:
            logger.debug("CloudFront not configured, skipping invalidation")
            return None

        try:
            response = self.cloudfront_client.create_invalidation(
                DistributionId=self.cloudfront_distribution_id,
                InvalidationBatch={
                    "Paths": {"Quantity": len(paths), "Items": paths},
                    "CallerReference": f"fmmap-{Path(paths[0]).name}",
                },
            )

            invalidation_id = response["Invalidation"]["Id"]
            logger.info(f"Created CloudFront invalidation: {invalidation_id}")

            return invalidation_id

        except ClientError as e:
            logger.error(f"Error creating CloudFront invalidation: {e}")
            raise

    def upload_audit_csv(self, local_path: str, s3_key: str) -> str:
        """Upload audit CSV to S3.

        Args:
            local_path: Local CSV file path
            s3_key: S3 object key

        Returns:
            S3 URL of uploaded file
        """
        try:
            local_file = Path(local_path)
            if not local_file.exists():
                raise FileNotFoundError(f"File not found: {local_path}")

            self.s3_client.upload_file(
                str(local_file),
                self.s3_bucket,
                s3_key,
                ExtraArgs={"ContentType": "text/csv"},
            )

            s3_url = (
                f"https://{self.s3_bucket}.s3.{self.aws_region}.amazonaws.com/{s3_key}"
            )

            logger.debug(f"Uploaded audit CSV to S3: {s3_url}")
            return s3_url

        except ClientError as e:
            logger.error(f"Error uploading audit CSV to S3: {e}")
            raise
