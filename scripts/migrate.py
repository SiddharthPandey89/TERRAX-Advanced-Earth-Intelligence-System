"""Apply numbered SQL migrations once, recording content checksums in Postgres."""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    import psycopg
except ImportError as exc:
    print("Migration dependencies are missing. Run INSTALL.bat or install geo-ml-service/requirements.txt.", file=sys.stderr)
    raise SystemExit(2) from exc


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is not configured; no database changes were made.", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(database_url, connect_timeout=8) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
            if not files:
                print(f"No migrations found in {MIGRATIONS}.", file=sys.stderr)
                return 1
            for path in files:
                version = path.name.split("_", 1)[0]
                content = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
                existing = connection.execute(
                    "SELECT filename, checksum FROM schema_migrations WHERE version = %s", (version,)
                ).fetchone()
                if existing:
                    if existing[0] != path.name or existing[1] != checksum:
                        print(f"Migration {path.name} differs from the applied checksum; refusing to continue.", file=sys.stderr)
                        return 1
                    print(f"already applied: {path.name}")
                    continue
                with connection.transaction():
                    connection.execute(content, prepare=False)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, filename, checksum) VALUES (%s, %s, %s)",
                        (version, path.name, checksum),
                    )
                print(f"applied: {path.name}")
        print("Database migrations are current.")
        return 0
    except Exception as exc:
        print(f"Database migration failed ({type(exc).__name__}). Check DATABASE_URL and database logs.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
