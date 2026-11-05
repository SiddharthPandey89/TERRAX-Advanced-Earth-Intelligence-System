
-- Enable spatial types and functions required by the GeoIntelligence platform.
-- IF NOT EXISTS keeps this migration safe to run more than once.
CREATE EXTENSION IF NOT EXISTS postgis;