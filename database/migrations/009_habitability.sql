-- Habitability assessment results produced by an analysis.
-- Scoring methodology and environmental thresholds are defined outside the database.
CREATE TABLE IF NOT EXISTS habitability_assessments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id BIGINT NOT NULL REFERENCES analyses(id) ON DELETE RESTRICT,
    overall_score NUMERIC,
    category TEXT NOT NULL CHECK (length(trim(category)) > 0),
    summary TEXT,
    factor_breakdown JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(factor_breakdown) = 'object'),
    confidence_score NUMERIC
        CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

