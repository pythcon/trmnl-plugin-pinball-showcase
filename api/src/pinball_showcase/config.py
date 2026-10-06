"""Runtime configuration, read from environment variables prefixed with ``PINBALL_``."""

from datetime import time
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_EXPORT_URL = "https://mp-data.sfo3.cdn.digitaloceanspaces.com/opdb-v2.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PINBALL_", env_file=".env", extra="ignore")

    # Where the OPDB daily export lives. Match Play rebuilds it around 06:30 UTC.
    opdb_export_url: str = DEFAULT_EXPORT_URL
    # Directory for the cached export (mount a volume here in Docker).
    data_dir: Path = Path("./data")
    # Daily refresh time (UTC). Defaults to shortly after the upstream rebuild.
    refresh_time_utc: time = time(7, 0)
    # A cached export older than this is re-downloaded at startup.
    max_age_hours: float = 26.0
    # Delay before retrying a failed download.
    retry_minutes: float = 15.0
    download_timeout_seconds: float = 120.0
    # Exports with fewer entries than this are treated as corrupt and rejected.
    min_entries: int = 500

    # Public address of this instance, used for machine-page links and the QR code.
    # Empty means "the address the request came in on" (fine behind a proxy that sends
    # X-Forwarded-Proto/Host). The hosted instance sets https://pinball-showcase.trmnlplugins.com.
    public_url: str = ""

    # Timezone used when a request does not send one.
    default_timezone: str = "UTC"
    # Cache-Control max-age for showcase responses.
    cache_max_age_seconds: int = 300

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
