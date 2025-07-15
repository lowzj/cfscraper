-- PostgreSQL initialization script for CFScraper development environment
-- This script sets up the database with proper permissions and extensions

-- Create extensions if they don't exist
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create additional schemas if needed
-- CREATE SCHEMA IF NOT EXISTS analytics;

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON DATABASE cfscraper_dev TO cfscraper;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cfscraper;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cfscraper;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cfscraper;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cfscraper;

-- Create indexes for better performance (will be created by Alembic migrations)
-- These are just examples and should match your actual schema

-- Log the initialization
INSERT INTO pg_stat_statements_info (dealloc) VALUES (0) ON CONFLICT DO NOTHING;
