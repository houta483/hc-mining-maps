"""Auto-discover mine areas from Box parent folder."""

import logging
from typing import List, Dict

from src.box_client import BoxClient
from boxsdk.exception import BoxValueError, BoxAPIException

logger = logging.getLogger(__name__)


def discover_mine_areas(box_client: BoxClient, parent_folder_id: str) -> List[Dict]:
    """Discover mine areas by scanning a parent folder.

    Args:
        box_client: Authenticated Box client
        parent_folder_id: Box folder ID (numeric) or share link ID (string)

    Returns:
        List of mine area dictionaries with name and box_folder_id
    """
    mine_areas = []

    try:
        # First, try to use it as a numeric folder ID
        folder = None
        if parent_folder_id.isdigit():
            try:
                folder = box_client.client.folder(parent_folder_id).get()
                logger.info(
                    f"Scanning parent folder: {folder.name} ({parent_folder_id})"
                )
            except BoxValueError:
                logger.error(f"Invalid numeric folder ID: {parent_folder_id}")
                raise

        # If not numeric, try to resolve from share link
        if not folder:
            logger.info(
                f"Attempting to resolve share link ID to folder: {parent_folder_id}"
            )
            try:
                # Box SDK requires the share password (if any) - try without first
                # Format: https://app.box.com/s/{share_link_id}
                share_url = f"https://app.box.com/s/{parent_folder_id}"
                shared_item = box_client.client.get_shared_item(share_url)

                if shared_item.type == "folder":
                    # Get the actual numeric folder ID
                    numeric_id = shared_item.id
                    folder = box_client.client.folder(numeric_id).get()
                    logger.info(
                        f"Resolved share link to folder: {folder.name} (ID: {numeric_id})"
                    )
                    # Update parent_folder_id for logging
                    parent_folder_id = numeric_id
                else:
                    raise ValueError(
                        f"Shared item is not a folder, it's a {shared_item.type}"
                    )
            except BoxAPIException as e:
                logger.error(f"Could not resolve share link ID: {e}")
                raise ValueError(
                    f"Invalid folder ID '{parent_folder_id}'. "
                    "If using a share link, make sure it's publicly accessible (or add the share password). "
                    "Alternatively, use the numeric folder ID from the Box URL (e.g., https://app.box.com/folder/1234567890)"
                )

        # List all items in parent folder
        items = list(folder.get_items())

        # Filter for folders (mine areas)
        for item in items:
            if item.type == "folder":
                mine_area_name = item.name
                mine_areas.append(
                    {
                        "name": mine_area_name,
                        "box_folder_id": item.id,
                    }
                )
                logger.info(
                    f"Discovered mine area: {mine_area_name} (folder ID: {item.id})"
                )

        logger.info(f"Found {len(mine_areas)} mine areas in parent folder")

    except Exception as e:
        logger.error(f"Error discovering mine areas: {e}", exc_info=True)
        raise

    return mine_areas
