-- MySQL initialization script for Borehole Analysis App
-- Creates users table for authentication

CREATE DATABASE IF NOT EXISTS borehole_db;
USE borehole_db;

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Note: Initial admin user will be created via script or migration
-- Example (hash for 'admin' password 'admin123'):
-- INSERT INTO users (username, password_hash) 
-- VALUES ('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYdJVSKzVjq');

