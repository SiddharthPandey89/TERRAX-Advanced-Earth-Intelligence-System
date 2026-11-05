"""Environment-based configuration for the Earth GeoIntelligence ML service.

Uses only the standard library. Values are read from environment variables,
validated once, and exposed as an immutable ``Settings`` object through
``get_settings()``.

Environment variables (all optional):
    APP_ENV           development | test | staging | production   (default: development)
    ML_SERVICE_HOST   interface to bind to                         (default: 0.0.0.0)
    ML_SERVICE_PORT   TCP port, 1-65535                            (default: 8000)
    LOG_LEVEL         debug | info | warning | error | critical    (default: info,
                      or debug when APP_ENV=development is not overridden)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
except ImportError:
    # Environment variables can still be supplied directly by a process manager.
    pass

SERVICE_NAME = "earth-geointelligence-ml-service"
SERVICE_VERSION = "0.1.0"

ALLOWED_ENVIRONMENTS = ("development", "test", "staging", "production")
ALLOWED_LOG_LEVELS = ("debug", "info", "warning", "error", "critical")

DEFAULT_ENVIRONMENT = "development"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "info"


class ConfigError(ValueError):
    """Raised when an environment variable holds an invalid value."""


def _read(name: str, default: str) -> str:
    """Return a stripped env value, treating unset or blank as the default."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _parse_environment(raw: str) -> str:
    value = raw.lower()
    value = {"dev": "development", "prod": "production"}.get(value, value)
    if value not in ALLOWED_ENVIRONMENTS:
        raise ConfigError(
            f"APP_ENV must be one of {', '.join(ALLOWED_ENVIRONMENTS)}; got {raw!r}."
        )
    return value


def _parse_host(raw: str) -> str:
    if any(ch.isspace() for ch in raw):
        raise ConfigError(f"ML_SERVICE_HOST must not contain whitespace; got {raw!r}.")
    return raw


def _parse_port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise ConfigError(f"ML_SERVICE_PORT must be an integer; got {raw!r}.") from None
    if not 1 <= port <= 65535:
        raise ConfigError(f"ML_SERVICE_PORT must be between 1 and 65535; got {port}.")
    return port


def _parse_log_level(raw: str) -> str:
    value = raw.lower()
    if value not in ALLOWED_LOG_LEVELS:
        raise ConfigError(
            f"LOG_LEVEL must be one of {', '.join(ALLOWED_LOG_LEVELS)}; got {raw!r}."
        )
    return value


@dataclass(frozen=True)
class Settings:
    """Validated, immutable runtime configuration."""

    service_name: str
    service_version: str
    environment: str
    host: str
    port: int
    log_level: str  # lowercase name, e.g. "info" (uvicorn-compatible)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are exposed everywhere except production."""
        return not self.is_production

    @property
    def log_level_name(self) -> str:
        """Uppercase level name, e.g. "INFO"."""
        return self.log_level.upper()

    @property
    def log_level_number(self) -> int:
        """Numeric level for the ``logging`` module."""
        return getattr(logging, self.log_level_name)


def load_settings() -> Settings:
    """Read and validate configuration from the current environment."""
    environment = _parse_environment(_read("APP_ENV", DEFAULT_ENVIRONMENT))

    # Development defaults to verbose logs; an explicit LOG_LEVEL always wins.
    default_level = "debug" if environment == "development" else DEFAULT_LOG_LEVEL

    return Settings(
        service_name=SERVICE_NAME,
        service_version=SERVICE_VERSION,
        environment=environment,
        host=_parse_host(_read("ML_SERVICE_HOST", DEFAULT_HOST)),
        port=_parse_port(_read("ML_SERVICE_PORT", str(DEFAULT_PORT))),
        log_level=_parse_log_level(_read("LOG_LEVEL", default_level)),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings; fails fast on invalid configuration."""
    return load_settings()
