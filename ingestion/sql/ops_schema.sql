-- Pipeline orchestration metadata
-- Run once: psql -U postgres -d denial_db -f ingestion/sql/ops_schema.sql

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_name   TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    steps           JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message   TEXT,
    triggered_by    TEXT DEFAULT 'manual'
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started
    ON ops.pipeline_runs (started_at DESC);

GRANT USAGE ON SCHEMA ops TO denial_user;
GRANT SELECT, INSERT, UPDATE ON ops.pipeline_runs TO denial_user;
