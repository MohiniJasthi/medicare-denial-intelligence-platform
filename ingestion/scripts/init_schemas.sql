-- ============================================================
-- init_schemas.sql
-- Bootstrap SQL run by PostgreSQL on first container start.
-- Creates the schema layers for the denial platform.
-- ============================================================

-- Raw ingestion layer (loaded by Python scripts)
CREATE SCHEMA IF NOT EXISTS raw;

-- dbt staging layer
CREATE SCHEMA IF NOT EXISTS staging;

-- dbt intermediate layer
CREATE SCHEMA IF NOT EXISTS intermediate;

-- dbt marts layer (analytical fact/dim tables)
CREATE SCHEMA IF NOT EXISTS marts;

-- ML feature store
CREATE SCHEMA IF NOT EXISTS features;

-- Grant usage to the application user
GRANT USAGE ON SCHEMA raw, staging, intermediate, marts, features
    TO denial_user;

GRANT CREATE ON SCHEMA raw, staging, intermediate, marts, features
    TO denial_user;
