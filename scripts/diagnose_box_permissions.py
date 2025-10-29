#!/usr/bin/env python3
"""
Diagnostic script to check Box API permissions and access.

Tests:
1. Can we list folders? (metadata access)
2. Can we get file info? (metadata access)
3. Can we download files? (content access)
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.box_client import BoxClient


def main():
    """Run diagnostic checks."""
    config_path = Path("secrets/box_config.json")

    if not config_path.exists():
        print(f"❌ Box config not found at {config_path}")
        return 1

    try:
        print("🔍 Initializing Box client...")
        client = BoxClient(str(config_path))
        print("✅ Box client authenticated\n")

        # Test 1: List a folder (metadata access)
        print("Test 1: Can we list folder contents?")
        print("-" * 50)
        test_folder_id = "348307991463"  # "Sieve Analyses" folder
        try:
            items = client.list_folder_contents(test_folder_id)
            print(f"✅ SUCCESS: Listed {len(items)} items in folder")
            if items:
                print(f"   First item: {items[0]['name']} ({items[0]['type']})")
        except Exception as e:
            print(f"❌ FAILED: {e}\n")
            return 1

        # Test 2: Get file metadata
        print("\nTest 2: Can we get file metadata?")
        print("-" * 50)
        if items:
            test_file_id = None
            for item in items:
                if item["type"] == "file":
                    test_file_id = item["id"]
                    break

            if test_file_id:
                try:
                    metadata = client.get_file_metadata(test_file_id)
                    print(f"✅ SUCCESS: Got metadata for file {metadata['name']}")
                    print(f"   Size: {metadata['size']} bytes")
                except Exception as e:
                    print(f"❌ FAILED: {e}\n")
                    return 1
            else:
                print("⚠️  No files found in test folder")

        # Test 3: Try to download (content access)
        print("\nTest 3: Can we download file content?")
        print("-" * 50)
        if test_file_id:
            try:
                # Try to get a small chunk to test content access
                file_obj = client.client.file(test_file_id)
                file_info = file_obj.get()
                print(f"✅ File info retrieved: {file_info.name}")

                # Try actual download
                import tempfile

                with tempfile.NamedTemporaryFile(delete=True) as tmp:
                    local_path = tmp.name

                client.download_file(test_file_id, local_path)
                print(f"✅ SUCCESS: Downloaded file to {local_path}")

            except Exception as e:
                print(f"❌ FAILED: {e}")
                print("\n🔍 Analysis:")
                error_str = str(e)
                if "403" in error_str or "permission" in error_str.lower():
                    print("   → This is a PERMISSION issue, not authentication")
                    print(
                        "   → The service account can see files but can't download them"
                    )
                    print("\n💡 Possible causes:")
                    print("   1. App needs to be RE-AUTHORIZED after enabling scopes")
                    print(
                        "   2. Box Shield or enterprise policies blocking API downloads"
                    )
                    print("   3. Files are owned by users with restricted permissions")
                    print("   4. Service account needs explicit download permissions")
                return 1
        else:
            print("⚠️  No files found to test download")

        print("\n" + "=" * 50)
        print("✅ All tests passed! Box API access is working correctly.")
        return 0

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
