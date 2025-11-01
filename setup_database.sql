-- Database Setup Script for Borehole Analysis App
-- Run this against the production RDS instance (hc-mining-db-ecs.ct084esas2t5.us-east-2.rds.amazonaws.com)
-- Replace <DB_PASSWORD> with the strong password you generate for production.

-- Step 1: Create database
CREATE DATABASE IF NOT EXISTS borehole_db;

-- Step 2: Create user and grant permissions
CREATE USER IF NOT EXISTS 'borehole_user'@'%' IDENTIFIED BY '<DB_PASSWORD>';
GRANT ALL PRIVILEGES ON borehole_db.* TO 'borehole_user'@'%';
FLUSH PRIVILEGES;

-- Step 3: Use the database and create schema
USE borehole_db;

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verify
SELECT 'Database setup complete!' AS status;
SELECT COUNT(*) AS tables_created FROM information_schema.tables WHERE table_schema = 'borehole_db';





