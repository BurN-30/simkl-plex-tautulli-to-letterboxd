"""Configuration loading from .env file."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Config:
    """Application configuration."""

    # Source
    PRIMARY_SOURCE: str = os.getenv("PRIMARY_SOURCE", "simkl")

    # Simkl
    SIMKL_CLIENT_ID: str = os.getenv("SIMKL_CLIENT_ID", "")
    SIMKL_TOKEN_FILE: Path = Path(os.getenv("SIMKL_TOKEN_FILE", ".simkl_token"))

    # Plex
    PLEX_URL: str = os.getenv("PLEX_URL", "http://localhost:32400")
    PLEX_TOKEN: str = os.getenv("PLEX_TOKEN", "")

    # Tautulli
    TAUTULLI_URL: str = os.getenv("TAUTULLI_URL", "http://localhost:8181")
    TAUTULLI_API_KEY: str = os.getenv("TAUTULLI_API_KEY", "")
    TAUTULLI_USER_ID: int = int(os.getenv("TAUTULLI_USER_ID", "1"))

    # TMDB
    TMDB_API_KEY: str = os.getenv("TMDB_API_KEY", "")

    # Options
    EXPORT_RATINGS: bool = os.getenv("EXPORT_RATINGS", "true").lower() == "true"
    EXPORT_WATCHLIST: bool = os.getenv("EXPORT_WATCHLIST", "true").lower() == "true"
    EXPORT_WATCHED: bool = os.getenv("EXPORT_WATCHED", "true").lower() == "true"
    SKIP_SERIES: bool = os.getenv("SKIP_SERIES", "true").lower() == "true"
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "./output"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Web interface
    WEB_PORT: int = int(os.getenv("WEB_PORT", "19876"))
    SYNC_INTERVAL: int = int(os.getenv("SYNC_INTERVAL", "15"))  # minutes

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration. Returns list of errors."""
        errors = []

        if cls.PRIMARY_SOURCE == "simkl" and not cls.SIMKL_CLIENT_ID:
            errors.append("SIMKL_CLIENT_ID is required when using Simkl source")

        if cls.PRIMARY_SOURCE == "plex" and not cls.PLEX_TOKEN:
            errors.append("PLEX_TOKEN is required when using Plex source")

        if cls.PRIMARY_SOURCE == "tautulli" and not cls.TAUTULLI_API_KEY:
            errors.append("TAUTULLI_API_KEY is required when using Tautulli source")

        if not cls.TMDB_API_KEY:
            errors.append("TMDB_API_KEY is required for enrichment")

        return errors

    @classmethod
    def ensure_directories(cls) -> None:
        """Create output and logs directories if they don't exist."""
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(parents=True, exist_ok=True)
