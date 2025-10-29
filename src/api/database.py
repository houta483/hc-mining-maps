"""MySQL database connection and queries."""

import logging
import os
from typing import Optional, Dict, Any
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)


class Database:
    """MySQL database connection manager."""

    def __init__(self):
        """Initialize database connection from environment variables."""
        self.host = os.environ.get("MYSQL_HOST", "mysql")
        self.port = int(os.environ.get("MYSQL_PORT", "3306"))
        self.user = os.environ.get("MYSQL_USER", "borehole_user")
        self.password = os.environ.get("MYSQL_PASSWORD", "")
        self.database = os.environ.get("MYSQL_DATABASE", "borehole_db")
        self._connection = None

    def connect(self):
        """Establish database connection."""
        try:
            self._connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                cursorclass=DictCursor,
                charset="utf8mb4",
                autocommit=True,
            )
            logger.info("Connected to MySQL database")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return False

    def disconnect(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Disconnected from MySQL database")

    def get_connection(self):
        """Get database connection (lazy connection)."""
        if self._connection is None or not self._connection.open:
            self.connect()
        return self._connection

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                query = (
                    "SELECT id, username, password_hash, created_at "
                    "FROM users WHERE username = %s"
                )
                cursor.execute(query, (username,))
                user = cursor.fetchone()
                return user
        except Exception as e:
            logger.error(f"Error fetching user: {e}")
            return None

    def create_user(self, username: str, password_hash: str) -> bool:
        """Create a new user."""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                query = "INSERT INTO users (username, password_hash) " "VALUES (%s, %s)"
                cursor.execute(query, (username, password_hash))
                logger.info(f"Created user: {username}")
                return True
        except pymysql.err.IntegrityError:
            logger.warning(f"User already exists: {username}")
            return False
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False


# Global database instance
db = Database()
