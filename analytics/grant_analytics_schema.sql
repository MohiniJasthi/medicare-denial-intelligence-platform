-- Run once if analytics schema was added after initial setup.
-- psql -U postgres -d denial_db -f analytics/grant_analytics_schema.sql

CREATE SCHEMA IF NOT EXISTS analytics;

GRANT USAGE ON SCHEMA analytics TO denial_user;
GRANT CREATE ON SCHEMA analytics TO denial_user;

-- After dbt run, grant read on analytics tables to denial_user (dbt creates as owner)
GRANT SELECT ON ALL TABLES IN SCHEMA public_analytics TO denial_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public_analytics
  GRANT SELECT ON TABLES TO denial_user;
