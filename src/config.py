"""Configuration, loaded from the .env file at the project root."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    """Read an env value, dropping any inline comment and surrounding space."""
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.split("#")[0].strip()


def _flag(key: str, default: str = "false") -> bool:
    return _env(key, default).lower() in {"1", "true", "yes", "on"}


def _int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _path(key: str, default: str) -> Path:
    value = _env(key, default)
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


PLACEHOLDERS = {
    "",
    "your_client_id",
    "your_client_secret",
    "your_plex_token",
    "your_api_key",
    "your_tmdb_api_key",
}


class Config:
    """Application configuration."""

    # Source selection
    PRIMARY_SOURCE: str = _env("PRIMARY_SOURCE", "simkl").lower()

    # Simkl
    SIMKL_CLIENT_ID: str = _env("SIMKL_CLIENT_ID")
    SIMKL_CLIENT_SECRET: str = _env("SIMKL_CLIENT_SECRET")
    SIMKL_TOKEN_FILE: Path = _path("SIMKL_TOKEN_FILE", "data/simkl_token.json")
    # Simkl returns last_watched_at in UTC. Bulk-imported films carry a
    # midnight marker, but films marked as watched live carry a real timestamp.
    # Converting those to Europe/Paris before truncating moves late-evening
    # watches to the following calendar day, which is not always what the user
    # means, so the conversion is opt-in for Simkl.
    SIMKL_CONVERT_TIMEZONE: bool = _flag("SIMKL_CONVERT_TIMEZONE", "false")

    # Plex
    PLEX_URL: str = _env("PLEX_URL", "http://localhost:32400")
    PLEX_TOKEN: str = _env("PLEX_TOKEN")

    # Tautulli
    TAUTULLI_URL: str = _env("TAUTULLI_URL", "http://localhost:8181")
    TAUTULLI_API_KEY: str = _env("TAUTULLI_API_KEY")
    TAUTULLI_USER_ID: int = _int("TAUTULLI_USER_ID", 1)

    # TMDB enrichment is entirely optional: without a key the tool relies on
    # the TMDB and IMDb ids that Simkl already provides.
    TMDB_API_KEY: str = _env("TMDB_API_KEY")

    # Behaviour
    LOCAL_TIMEZONE: str = _env("LOCAL_TIMEZONE", "Europe/Paris")
    EXPORT_WATCHLIST: bool = _flag("EXPORT_WATCHLIST", "true")
    SKIP_SERIES: bool = _flag("SKIP_SERIES", "true")
    MAX_CSV_BYTES: int = _int("MAX_CSV_BYTES", 950_000)

    # Paths
    OUTPUT_DIR: Path = _path("OUTPUT_DIR", "output")
    DATA_DIR: Path = _path("DATA_DIR", "data")
    LOG_DIR: Path = _path("LOG_DIR", "logs")
    DB_PATH: Path = _path("DB_PATH", "data/movies.db")

    # Logging
    LOG_LEVEL: str = _env("LOG_LEVEL", "INFO").upper()
    CONSOLE_LOG_LEVEL: str = _env("CONSOLE_LOG_LEVEL", "INFO").upper()

    # Web dashboard
    WEB_PORT: int = _int("WEB_PORT", 19876)
    OAUTH_PORT: int = _int("OAUTH_PORT", 19877)

    @classmethod
    def pending_dir(cls) -> Path:
        return cls.OUTPUT_DIR / "pending"

    @classmethod
    def done_dir(cls) -> Path:
        return cls.OUTPUT_DIR / "done"

    @classmethod
    def tmdb_enabled(cls) -> bool:
        return cls.TMDB_API_KEY not in PLACEHOLDERS

    @classmethod
    def validate(cls) -> list[str]:
        """Return the list of blocking configuration problems."""
        errors: list[str] = []

        if cls.PRIMARY_SOURCE not in {"simkl", "plex", "tautulli"}:
            errors.append(f"PRIMARY_SOURCE must be simkl, plex or tautulli (got {cls.PRIMARY_SOURCE!r})")

        if cls.PRIMARY_SOURCE == "simkl":
            if cls.SIMKL_CLIENT_ID in PLACEHOLDERS:
                errors.append("SIMKL_CLIENT_ID is required - see simkl.com/settings/developer")
            if cls.SIMKL_CLIENT_SECRET in PLACEHOLDERS:
                errors.append("SIMKL_CLIENT_SECRET is required - see simkl.com/settings/developer")

        if cls.PRIMARY_SOURCE == "plex" and cls.PLEX_TOKEN in PLACEHOLDERS:
            errors.append("PLEX_TOKEN is required when PRIMARY_SOURCE=plex")

        if cls.PRIMARY_SOURCE == "tautulli" and cls.TAUTULLI_API_KEY in PLACEHOLDERS:
            errors.append("TAUTULLI_API_KEY is required when PRIMARY_SOURCE=tautulli")

        return errors

    @classmethod
    def ensure_directories(cls) -> None:
        for directory in (cls.OUTPUT_DIR, cls.pending_dir(), cls.done_dir(), cls.DATA_DIR, cls.LOG_DIR):
            directory.mkdir(parents=True, exist_ok=True)
