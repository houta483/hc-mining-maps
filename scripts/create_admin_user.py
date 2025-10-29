#!/usr/bin/env python3
"""Script to create an admin user in the database."""

import sys
import os
import bcrypt
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.api.database import Database


def create_user(username: str, password: str):
    """Create a new user in the database."""
    db = Database()

    if not db.connect():
        print("❌ Failed to connect to database")
        sys.exit(1)

    # Hash password
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )

    # Create user
    if db.create_user(username, password_hash):
        print(f"✅ Created user: {username}")
    else:
        print(f"❌ Failed to create user: {username}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("username", help="Username")
    parser.add_argument("password", help="Password")

    args = parser.parse_args()
    create_user(args.username, args.password)


if __name__ == "__main__":
    main()
