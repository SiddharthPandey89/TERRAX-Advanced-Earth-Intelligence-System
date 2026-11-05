-- Individual environmental measurements linked to a region and source dataset.
-- Point coordinates use WGS 84 (SRID 4326) with longitude as X and latitude as Y.
CREATE TABLE IF NOT EXISTS observations (
id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
region_id BIGINT NOT NULL REFERENCES regions(id) ON DELETE RESTRICT,
dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE RESTRICT,
variable_name TEXT NOT NULL CHECK (length(trim(variable_name)) > 0),
measurement_value NUMERIC NOT NULL,
measurement_unit TEXT,
observed_at TIMESTAMPTZ NOT NULL,
location geometry(Point, 4326),
metadata JSONB NOT NULL DEFAULT '{}'::JSONB
CHECK (jsonb_typeof(metadata) = 'object'),
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

