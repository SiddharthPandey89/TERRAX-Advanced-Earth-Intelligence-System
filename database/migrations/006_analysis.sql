-- Tracks analysis jobs and execution metadata for a selected geographic region.
CREATE TABLE IF NOT EXISTS analyses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id BIGINT NOT NULL REFERENCES regions(id) ON DELETE RESTRICT,
    initiated_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    analysis_type TEXT NOT NULL CHECK (length(trim(analysis_type)) > 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(parameters) = 'object'),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT CHECK (duration_ms IS NULL OR duration_ms >= 0),
    result_metadata JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(result_metadata) = 'object'),
    error_details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT analyses_completion_time_check
        CHECK (
            completed_at IS NULL
            OR started_at IS NULL
            OR completed_at >= started_at
        )
);

