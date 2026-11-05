-- Estimated geological resource prospectivity results produced by an analysis.
-- A prospectivity score is an evidence-based estimate, not proof of a discovery or reserve.
-- prospectivity_score uses a 0–100 scale when provided; it is not necessarily a verified probability.
CREATE TABLE IF NOT EXISTS prospectivity_assessments (
id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
analysis_id BIGINT NOT NULL REFERENCES analyses(id) ON DELETE RESTRICT,
resource_name TEXT NOT NULL CHECK (length(trim(resource_name)) > 0),
resource_category TEXT NOT NULL CHECK (length(trim(resource_category)) > 0),
prospectivity_score NUMERIC
CHECK (
prospectivity_score IS NULL
OR prospectivity_score BETWEEN 0 AND 100
),
classification TEXT NOT NULL CHECK (length(trim(classification)) > 0),
confidence_score NUMERIC
CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
summary TEXT,
evidence JSONB NOT NULL DEFAULT '{}'::JSONB
CHECK (jsonb_typeof(evidence) = 'object'),
assessed_at TIMESTAMPTZ,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

