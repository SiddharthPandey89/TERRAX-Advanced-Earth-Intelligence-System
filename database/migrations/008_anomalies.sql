-- Anomaly records detected during environmental and geospatial analyses.
-- Point coordinates use WGS 84 (SRID 4326) with longitude as X and latitude as Y.
CREATE TABLE IF NOT EXISTS anomalies (
id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
analysis_id BIGINT NOT NULL REFERENCES analyses(id) ON DELETE RESTRICT,
anomaly_type TEXT NOT NULL CHECK (length(trim(anomaly_type)) > 0),
description TEXT NOT NULL CHECK (length(trim(description)) > 0),
severity TEXT NOT NULL DEFAULT 'medium'
CHECK (severity IN ('low', 'medium', 'high', 'critical')),
detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
observed_start_at TIMESTAMPTZ,
observed_end_at TIMESTAMPTZ,
measured_value NUMERIC,
baseline_value NUMERIC,
anomaly_score NUMERIC,
location geometry(Point, 4326),
details JSONB NOT NULL DEFAULT '{}'::JSONB
CHECK (jsonb_typeof(details) = 'object'),
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
CONSTRAINT anomalies_observed_interval_check
CHECK (
observed_start_at IS NULL
OR observed_end_at IS NULL
OR observed_end_at >= observed_start_at
)
);
