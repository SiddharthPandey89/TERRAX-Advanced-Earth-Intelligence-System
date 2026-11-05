# Earth / GeoIntelligence Intelligence Platform

A CPU-first geospatial screening application built on the existing React/Vite frontend, Node.js/Express API, Python/FastAPI geospatial service, and optional PostgreSQL/PostGIS database. Provider-backed values, derived statistics, model outputs, and missing evidence are labelled separately; the application does not fill missing measurements or claim geological discoveries.

## Windows 11 quick start

1. Extract the complete ZIP to a writable folder (avoid a protected `Program Files` location).
2. Install Node.js 20+ and Python 3.10–3.12, and enable PATH or the Python Launcher (`py`). No CUDA or GPU setup is required.
3. Double-click `INSTALL.bat` once. It verifies runtime versions, creates `.venv`, installs the Python/geospatial and npm workspace dependencies, creates `.env` and `frontend/.env` from their examples, and creates `logs/`. It does not start any service.
4. Optional: edit `.env` only if enabling local PostGIS or setting provider values. The base website, place search, weather and elevation indicators do not need an API key. OpenStreetMap Nominatim search requires a real identifying `OSM_USER_AGENT` contact value.
5. Double-click `START.bat`. It checks dependencies/configuration/ports, starts the FastAPI service, Express API and Vite website, waits for health checks, then opens `http://127.0.0.1:5173` in the default browser. Keep the status window open or close it after the browser opens; managed services run separately and write to `logs/`.
6. Double-click `STOP.bat` to stop only processes verified as launched by this project. It stops the PostGIS container only when START itself started it.

If installation fails, read the message in the window and the service logs. Startup will not kill unrelated applications to free a port. Update the port setting or close the conflicting application yourself.

## Geographic analysis workflow

The existing map, place search, point weather view and habitability screen remain available. The **Analyze a bounded region** panel accepts west, south, east and north WGS84 bounds. **Use selected point ± 0.05°** prefills an editable bounding box; you can also enter the bounds directly. Submitting requests the live indicator catalog and source-backed values through `React → Express → FastAPI`.

Configured indicator sources are:

- **Temperature and rainfall/precipitation:** Open-Meteo Forecast API for current weather, or its Historical Weather API for an explicitly supplied date period. Point-weather values and daily-series statistics are labelled; they are not presented as ground-station measurements or area averages.
- **Elevation:** USGS 3DEP Elevation Point Query Service when its US coverage includes the selected representative point. It is a DEM point sample, not a survey or area-wide terrain summary.
- **Water availability/level, forest density, land cover, and fire:** shown as unavailable until an actual suitable data source is retrieved and processed. Nothing is imputed.

NASA Earthdata MODIS and Copernicus Sentinel provide bounded catalog discovery; USGS also provides bounded elevation/geological-product search. OpenStreetMap Nominatim supports user-triggered place search when its identifying User-Agent is configured. Discovery results describe returned metadata only: they are not processed raster indicators. Credential-protected assets are not downloaded at startup.

**Trends & anomalies** accepts a caller-supplied series with a named source and unit. The trend uses observation order when no timestamps are supplied. **Evidence-based habitability** applies the existing heuristic scoring model to explicitly entered factor JSON and withholds a score when its essential-input or coverage requirements are unmet. **Mineral, petroleum and gas potential** requires sourced criterion evidence and is explicitly an unconfirmed screening potential, never a discovery or reserve claim. Submitted input provenance is not independently verified by the application.

## Services and API

- Frontend: `http://127.0.0.1:5173`
- Express health: `GET http://127.0.0.1:5000/api/health`
- FastAPI health: `GET http://127.0.0.1:8000/health`
- FastAPI interactive documentation: `http://127.0.0.1:8000/docs` when `APP_ENV` is development, test or staging. Production hides the docs.

Express provides a fixed, allowlisted ML proxy under `/api/ml`:

- `GET /api/ml/indicators/catalog`
- `POST /api/ml/indicators/analyze`
- `GET /api/ml/ingestion/providers`
- `POST /api/ml/ingestion/{provider}/search` (`nasa-modis`, `copernicus-sentinel`, `usgs-elevation`, `usgs-geology`, `openstreetmap`)
- `POST /api/ml/habitability/analyze`
- `POST /api/ml/patterns/analyze`
- `POST /api/ml/prospectivity/analyze`

FastAPI also offers bounded GeoTIFF inspection/quality/reprojection/clip/mask and GeoJSON validation under `/preprocessing`. Uploads have file-size, format and pixel/sample limits; the API accepts no client-selected server path and removes temporary files after completion/streaming.

## Optional PostgreSQL/PostGIS

The point/weather workflow and analytical APIs run without PostgreSQL. The Docker Compose file retains its existing services; the Windows START script targets only its `postgres` service when Docker is installed and optional database settings contain a non-placeholder password. The database port is bound to loopback.

To enable PostGIS:

1. Copy `.env.example` to `.env` if not already created.
2. Set `POSTGRES_PASSWORD` to a unique local password and update `DATABASE_URL` to match. URL-encode reserved characters in passwords.
3. Double-click `START.bat`; if Docker Desktop is running, it starts PostGIS and attempts the numbered migrations. Or run `docker compose up -d postgres` yourself.
4. If you already run PostgreSQL with PostGIS locally, set `DATABASE_URL` to that database and apply migrations using `.venv\Scripts\python.exe scripts\migrate.py` from PowerShell.

The migration runner records filenames and SHA-256 checksums in `schema_migrations`; it refuses to silently rerun an edited migration. `scripts/seed_database.py` is retained as a compatibility alias for migrations only and does not insert invented measurements. Without Docker, install PostgreSQL plus PostGIS 3.4, create the database/user, set the same environment variables, then run the migration command.

Database-backed region functions remain unavailable until a real database connection exists. No database password is shipped. The provided `.env.example` contains placeholders only; never commit a populated `.env`.

## Configuration

Root `.env` supports `APP_ENV`, `NODE_ENV`, `PORT`, `ML_SERVICE_URL`, `ML_SERVICE_HOST`, `ML_SERVICE_PORT`, `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `CORS_ORIGIN`. Optional provider values include `NASA_EARTHDATA_TOKEN`, `COPERNICUS_ACCESS_TOKEN`, `COPERNICUS_STAC_URL`, `OSM_USER_AGENT`, `OSM_NOMINATIM_URL`, `OSM_HTTP_REFERER`, and `USGS_TNM_ENDPOINT`. Leave optional credentials unset if unused. `APP_ENV=dev` and `APP_ENV=prod` are normalized to development and production.

`frontend/.env` holds browser-visible `VITE_API_BASE_URL` only; never put credentials in a `VITE_` variable. If you change `PORT` in root `.env`, update `VITE_API_BASE_URL`; if you change `ML_SERVICE_PORT`, also update `ML_SERVICE_URL` so Express reaches FastAPI.

## Developer checks and manual startup

After running `INSTALL.bat`:

```powershell
npm test
npm run build
$env:PYTHONPATH = "geo-ml-service"
.\.venv\Scripts\python.exe -m unittest discover -s geo-ml-service\tests -v
```

To run services manually, start these in separate terminals from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir geo-ml-service --host 127.0.0.1 --port 8000
npm --workspace backend start
npm --workspace frontend run dev -- --host 127.0.0.1
```

Operational helper commands include `scripts/health_check.py`, `scripts/run_analysis.py` (point-weather analysis), `scripts/download_data.py` (provider catalog discovery only) and `scripts/preprocess_data.py` (secure raster upload operations).

## Resource and data limitations

The project uses CPU-compatible dependencies and does not download neural models or require a GPU. It does not ship satellite rasters, API keys, trained model artifacts, or preloaded scientific datasets. Full area-level climate/vegetation/fire/water products require acquiring source assets with their actual coverage, temporal range, attribution and license, then processing those data. External provider outages, coverage gaps, missing credentials and insufficient inputs are returned as unavailable/insufficient states.

`cpp/` remains optional: the audited repository contains no implemented C++ algorithms or build target. Geospatial operations implemented here use the existing Python raster, Shapely and PyProj modules.
