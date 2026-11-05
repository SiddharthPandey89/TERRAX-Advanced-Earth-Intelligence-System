-- Metadata for scientific and geospatial datasets; large data files remain external.
CREATE TABLE IF NOT EXISTS datasets (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    description TEXT,
    dataset_type TEXT NOT NULL CHECK (length(trim(dataset_type)) > 0),
    source_provider TEXT NOT NULL CHECK (length(trim(source_provider)) > 0),
    source_url TEXT,
    data_format TEXT NOT NULL CHECK (length(trim(data_format)) > 0),
    measurement_units TEXT,
    coverage_start_date DATE,
    coverage_end_date DATE,
    spatial_reference_srid INTEGER CHECK (spatial_reference_srid IS NULL OR spatial_reference_srid > 0),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(metadata) = 'object'),
    storage_location TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT datasets_coverage_dates_check
        CHECK (
            coverage_start_date IS NULL
            OR coverage_end_date IS NULL
            OR coverage_end_date >= coverage_start_date
        )
);

