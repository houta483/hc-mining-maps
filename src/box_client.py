"""Box client for authentication and file operations."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

from boxsdk import Client, JWTAuth, CCGAuth
from boxsdk.exception import BoxAPIException, BoxOAuthException

logger = logging.getLogger(__name__)


class BoxClient:
    """Client for interacting with Box API."""

    def __init__(self, config_path: str):
        """Initialize Box client with JWT or CCG authentication.

        Supports both JWT (with keypair) and CCG (Client Credentials Grant).

        Args:
            config_path: Path to Box config JSON file
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Box config not found at {config_path}")

        # Load config to determine auth method
        with open(config_path) as f:
            config = json.load(f)

        # Check if using CCG (simpler) or JWT
        box_settings = config.get("boxAppSettings", {})
        app_auth = box_settings.get("appAuth", {})

        if app_auth.get("privateKey"):
            # JWT authentication with As-User impersonation
            logger.debug("Using JWT authentication")
            auth = JWTAuth.from_settings_file(config_path)
            auth.authenticate_instance()
            admin_client = Client(auth)

            # Use As-User if specified
            as_user_id = os.environ.get("BOX_AS_USER_ID")
            if as_user_id:
                logger.debug("Impersonating a Box user via As-User")
                from boxsdk.object.user import User

                user = User(admin_client.session, as_user_id)
                self.client = admin_client.as_user(user)
            else:
                self.client = admin_client
        else:
            # CCG authentication (OAuth 2.0 Client Credentials Grant)
            logger.debug("Using CCG authentication")
            client_id = box_settings.get("clientID")
            client_secret = box_settings.get("clientSecret")

            if not all([client_id, client_secret]):
                raise ValueError("CCG auth requires clientID and clientSecret")

            as_user_id = os.environ.get("BOX_AS_USER_ID")
            if as_user_id:
                logger.debug("Using CCG As-User impersonation")
                try:
                    auth = CCGAuth(
                        client_id=client_id,
                        client_secret=client_secret,
                        user=as_user_id,
                    )
                    auth.authenticate_user()
                except BoxOAuthException as e:
                    error_msg = str(e)
                    is_invalid_grant = (
                        "invalid_grant" in error_msg
                        or "Grant credentials are invalid" in error_msg
                    )
                    if is_invalid_grant:
                        logger.error(
                            "=" * 80 + "\n"
                            "BOX AS-USER IMPERSONATION FAILED\n"
                            "=" * 80 + "\n"
                            "The Box app is not authorized to impersonate "
                            "users.\n"
                            "To fix this:\n"
                            "1. Go to https://app.box.com/developers/console\n"
                            "2. Select your app\n"
                            "3. Go to 'Authorization' tab\n"
                            "4. Ensure the app has 'Manage Users' scope "
                            "enabled\n"
                            "5. Contact a Box Admin to authorize the app for "
                            "user impersonation\n"
                            "   (Settings > Apps > Custom Apps > [Your App] > "
                            "Authorize)\n\n"
                            f"User ID: {as_user_id}\n"
                            f"Error: {error_msg}\n"
                            "=" * 80
                        )
                        # Try to fall back to enterprise token if available
                        enterprise_id = config.get("enterpriseID")
                        if enterprise_id:
                            logger.warning("Falling back to enterprise token")
                            auth = CCGAuth(
                                client_id=client_id,
                                client_secret=client_secret,
                                enterprise_id=enterprise_id,
                            )
                            auth.authenticate_instance()
                        else:
                            raise RuntimeError(
                                "Cannot proceed without As-User "
                                "impersonation or enterprise token. "
                                "Please fix the Box app authorization or "
                                "remove BOX_AS_USER_ID to use enterprise "
                                "token."
                            ) from e
                    else:
                        # Re-raise other OAuth errors
                        raise
            else:
                # Enterprise token (fallback if no As-User specified)
                logger.debug("Using CCG enterprise token")
                enterprise_id = config.get("enterpriseID")
                if not enterprise_id:
                    raise ValueError("CCG enterprise token requires enterpriseID")
                auth = CCGAuth(
                    client_id=client_id,
                    client_secret=client_secret,
                    enterprise_id=enterprise_id,
                )
                auth.authenticate_instance()

            self.client = Client(auth)

        # Verify which user we're acting as
        me = None
        me_id = None
        try:
            me = self.client.user().get()
            me_id = str(me.id) if hasattr(me, "id") else None
            logger.debug("Authenticated to Box")
        except Exception as e:
            logger.warning(f"Could not verify user identity: {e}")

        # Check folder permissions for debugging
        try:
            # Try to check a known folder's collaborations
            test_folder_id = os.environ.get("BOX_TEST_FOLDER_ID")
            if test_folder_id:
                folder = self.client.folder(test_folder_id).get()
                collabs = list(folder.get_collaborations())
                logger.debug("Checked folder collaborations for access validation")
            if me_id:
                logger.debug("Validating service account access")
            service_account_found = False
            for collab in collabs:
                role = getattr(collab, "role", "N/A")
                collab_type = getattr(collab.accessible_by, "type", "N/A")
                if collab_type == "user":
                    collab_id = getattr(collab.accessible_by, "id", None)
                    if me_id:  # Only log comparison when we have me_id
                        if collab_id and str(collab_id) == me_id:
                            service_account_found = True
                            logger.info(
                                "Service account ID %s has %s access",
                                me_id,
                                role,
                            )
                    if me_id and collab_id and str(collab_id) == me_id:
                        service_account_found = True
            if me_id and service_account_found:
                logger.debug("Service account permissions confirmed")
            if me_id and not service_account_found:
                logger.warning(
                    "Service account ID %s not found among collaborators",
                    me_id,
                )
        except Exception as e:
            logger.warning(f"Could not check folder collaborations: {e}")

        logger.debug("Box client authenticated successfully")

    def probe_download_rights(self, file_id: str) -> Dict:
        """Return key permission flags used to diagnose 403s on downloads."""
        try:
            f = self.client.file(file_id).get(
                fields=[
                    "name",
                    "permissions",
                    "can_download",
                    "classification",
                    "is_download_available",
                ]
            )
            info = {
                "name": f.name,
                "can_download": getattr(f, "can_download", None),
                "is_download_available": getattr(f, "is_download_available", None),
                "permissions": getattr(f, "permissions", None),
                "classification": getattr(f, "classification", None),
            }
            logger.debug("Downloaded permissions probe for file")
            return info
        except BoxAPIException as e:
            logger.error(f"Probe failed for file {file_id}: {e}")
            raise

    def list_folder_contents(self, folder_id: str) -> List[Dict]:
        """List all items in a Box folder.

        Args:
            folder_id: Box folder ID

        Returns:
            List of items (files and folders) with metadata
        """
        try:
            folder = self.client.folder(folder_id).get()
            items = []
            for item in folder.get_items():
                items.append(
                    {
                        "id": item.id,
                        "name": item.name,
                        "type": item.type,
                        "parent": {"id": folder_id},
                    }
                )
            logger.info(f"Found {len(items)} items in folder {folder_id}")
            return items
        except BoxAPIException as e:
            logger.error(f"Error listing folder {folder_id}: {e}")
            raise

    def download_file(self, file_id: str, local_path: str) -> str:
        """Download a file from Box to local filesystem.

        Args:
            file_id: Box file ID
            local_path: Local file path to save to

        Returns:
            Path to downloaded file
        """
        try:
            file_obj = self.client.file(file_id)

            # Check download availability (fail fast if disabled)
            try:
                file_info = file_obj.get(
                    fields=["is_download_available", "permissions", "name"]
                )
                if (
                    hasattr(file_info, "is_download_available")
                    and not file_info.is_download_available
                ):
                    raise RuntimeError(
                        f"Download blocked for {file_id} ({file_info.name}), "
                        f"permissions={getattr(file_info, 'permissions', 'N/A')}"
                    )
            except BoxAPIException:
                # If we can't check, proceed anyway
                pass

            # Download using As-User context (should have proper permissions)
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                file_obj.download_to(f)

            logger.debug(f"Downloaded file {file_id} to {local_path}")
            return local_path

        except BoxAPIException as e:
            if e.status == 403:
                logger.error(
                    f"403 Download denied for file {file_id}. "
                    "Possible causes:\n"
                    "1. Box Shield policy blocking API downloads\n"
                    "2. Enterprise-level API download restrictions\n"
                    "3. App OAuth scope insufficient (need 'Read all files')\n"
                    f"Error: {e}"
                )
            else:
                logger.error(f"Error downloading file {file_id}: {e}")
            raise
        except RuntimeError as e:
            logger.error(f"Download blocked: {e}")
            raise

    def get_file_link(self, file_id: str, access: str = "collaborators") -> str:
        """Return an existing link for a file without modifying Box state.

        Args:
            file_id: Box file ID
            access: Retained for backwards compatibility; unused.

        Returns:
            URL that can be used to open the file in Box.
        """
        try:
            file_item = self.client.file(file_id)

            # Attempt to fetch an existing shared link without creating one.
            try:
                file_info = file_item.get(fields=["shared_link"])
                shared_link = getattr(file_info, "shared_link", None)
                if shared_link and shared_link.get("url"):
                    logger.debug(f"Using existing shared link for file {file_id}")
                    return shared_link["url"]
            except BoxAPIException as link_error:
                logger.debug(
                    "Could not retrieve shared link for file %s: %s",
                    file_id,
                    link_error,
                )

            # Fall back to standard Box preview URL (requires user permissions).
            fallback_url = f"https://app.box.com/file/{file_id}"
            logger.info(
                "No shared link available for file %s; falling back to preview URL",
                file_id,
            )
            return fallback_url

        except BoxAPIException as e:
            logger.error(f"Error retrieving link for {file_id}: {e}")
            raise

    def get_file_metadata(self, file_id: str) -> Dict:
        """Get metadata for a Box file.

        Args:
            file_id: Box file ID

        Returns:
            File metadata dictionary
        """
        try:
            file_item = self.client.file(file_id).get()
            return {
                "id": file_item.id,
                "name": file_item.name,
                "size": file_item.size,
                "modified_at": file_item.modified_at,
            }
        except BoxAPIException as e:
            logger.error(f"Error getting metadata for {file_id}: {e}")
            raise

    def walk_folder_tree(self, folder_id: str) -> List[Tuple[str, List[Dict]]]:
        """Recursively walk folder tree and return (hole_folder_name, files) tuples.

        Args:
            folder_id: Root mine area folder ID

        Returns:
            List of (hole_folder_name, files) tuples
        """
        results = []
        try:
            folder = self.client.folder(folder_id).get()
            logger.debug("Walking folder tree from root folder")

            # Get all items in the mine area folder
            for item in folder.get_items():
                if item.type == "folder":
                    # This is a hole folder (e.g., T3, T2)
                    hole_name = item.name
                    hole_files = []

                    # Get all Excel files in the hole folder
                    for sub_item in item.get_items():
                        if sub_item.type == "file" and sub_item.name.lower().endswith(
                            (".xlsx", ".xls")
                        ):
                            hole_files.append(
                                {
                                    "id": sub_item.id,
                                    "name": sub_item.name,
                                    "parent_folder": hole_name,
                                }
                            )

                    if hole_files:
                        results.append((hole_name, hole_files))
                        logger.debug("Found %d files in a hole folder", len(hole_files))

        except BoxAPIException as e:
            logger.error(f"Error walking folder tree: {e}")
            raise

        return results
