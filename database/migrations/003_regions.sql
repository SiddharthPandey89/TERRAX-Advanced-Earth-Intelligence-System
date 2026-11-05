-- Geographic regions selected or defined for GeoIntelligence analysis.
CREATE TABLE IF NOT EXISTS regions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    description TEXT,
    region_type TEXT NOT NULL CHECK (length(trim(region_type)) > 0),
    boundary geometry(Geometry, 4326) NOT NULL,
    created_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT regions_boundary_type_check
        CHECK (ST_GeometryType(boundary) IN ('ST_Polygon', 'ST_MultiPolygon')),
    CONSTRAINT regions_boundary_non_empty_check
        CHECK (NOT ST_IsEmpty(boundary)),
    CONSTRAINT regions_boundary_valid_check
        CHECK (ST_IsValid(boundary))
);
