-- Calculated or derived indicator values produced by an analysis.
CREATE TABLE IF NOT EXISTS indicators (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id BIGINT NOT NULL REFERENCES analyses(id) ON DELETE RESTRICT,
    indicator_name TEXT NOT NULL CHECK (length(trim(indicator_name)) > 0),
    indicator_value NUMERIC NOT NULL,
    measurement_unit TEXT,
    classification TEXT,
    calculated_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

