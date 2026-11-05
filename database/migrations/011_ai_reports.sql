-- AI-generated reports summarizing evidence from a completed or related analysis.
CREATE TABLE IF NOT EXISTS ai_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id BIGINT NOT NULL REFERENCES analyses(id) ON DELETE RESTRICT,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    report_type TEXT NOT NULL CHECK (length(trim(report_type)) > 0),
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    summary TEXT,
    model_identifier TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(metadata) = 'object'),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

