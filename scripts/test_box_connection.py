#!/usr/bin/env python3
"""Test script to validate Box connection and credentials."""

import json
import os
import sys
from pathlib import Path

try:
    from boxsdk import Client, JWTAuth, CCGAuth
    from boxsdk.exception import BoxAPIException
except ImportError:
    print("ERROR: boxsdk not installed. Run: pip install boxsdk")
    sys.exit(1)


def test_box_connection():
    """Test Box connection with provided credentials."""
    config_path = os.environ.get("BOX_CONFIG", "secrets/box_config.json")

    print(f"Looking for Box config at: {config_path}")

    if not Path(config_path).exists():
        print(f"❌ ERROR: Box config file not found at {config_path}")
        print("\nPlease create secrets/box_config.json with your Box credentials.")
        sys.exit(1)

    try:
        print("✓ Config file found")
        print("Attempting to authenticate with Box...")

        # Load config to determine auth method
        with open(config_path) as f:
            config = json.load(f)

        box_settings = config.get("boxAppSettings", {})
        app_auth = box_settings.get("appAuth", {})

        # Check if using CCG or JWT
        if app_auth.get("privateKey"):
            # JWT authentication
            print("Using JWT authentication...")
            auth = JWTAuth.from_settings_file(config_path)
            auth.authenticate_instance()
            client = Client(auth)
        else:
            # CCG authentication
            print("Using CCG authentication...")
            client_id = box_settings.get("clientID")
            client_secret = box_settings.get("clientSecret")
            enterprise_id = config.get("enterpriseID")

            if not all([client_id, client_secret, enterprise_id]):
                print("❌ ERROR: CCG requires clientID, clientSecret, and enterpriseID")
                return False

            auth = CCGAuth(
                client_id=client_id,
                client_secret=client_secret,
                enterprise_id=enterprise_id,
            )
            auth.authenticate_instance()
            client = Client(auth)

        print("✓ Successfully authenticated with Box!")

        # Get current user info
        user = client.user().get()
        print(f"✓ Connected as: {user.name} ({user.login})")

        # Try to list a test folder (optional - will fail if no folder ID provided)
        test_folder_id = os.environ.get("TEST_FOLDER_ID")
        if test_folder_id:
            print(f"\nTesting folder access: {test_folder_id}")
            try:
                folder = client.folder(test_folder_id).get()
                print(f"✓ Can access folder: {folder.name}")
                items = list(folder.get_items())
                print(f"✓ Found {len(items)} items in folder")
                for item in items[:5]:  # Show first 5 items
                    print(f"  - {item.name} ({item.type})")
            except BoxAPIException as e:
                print(f"⚠ Warning: Could not access test folder: {e}")
        else:
            print("\n(Set TEST_FOLDER_ID env var to test folder access)")

        print("\n✅ Box connection test PASSED!")
        return True

    except BoxAPIException as e:
        print(f"\n❌ Box API Error: {e}")
        print("\nCommon issues:")
        print("  1. App not approved by admin yet")
        print("  2. Invalid credentials in box_config.json")
        print("  3. Service Account not invited to folders")
        return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nCheck that your box_config.json is properly formatted.")
        return False


if __name__ == "__main__":
    success = test_box_connection()
    sys.exit(0 if success else 1)
