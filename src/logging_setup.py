"""Logging configuration: rotating file handler plus console."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

_FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_CONSOLE_FORMAT = "%(levelname)-7s %(message)s"

#: Environment variables and settings that must never reach a log record.
_SECRET_KEYS = ("client_secret", "access_token", "api_key", "apikey", "token")


class SecretFilter(logging.Filter):
    """Drop records that would print a credential.

    Nothing in the codebase logs a secret on purpose; this is a backstop for
    third-party libraries that log request URLs with an ``apikey`` query
    parameter.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage().lower()
        except Exception:  # pragma: no cover - defensive
            return True
        return not any(f"{key}=" in message for key in _SECRET_KEYS)


def setup_logging(
    log_dir: Path,
    level: str = "INFO",
    console_level: Optional[str] = None,
    filename: str = "letterboxd-sync.log",
) -> None:
    """Configure the root logger for a CLI run."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / filename,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    file_handler.addFilter(SecretFilter())
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(getattr(logging, (console_level or level).upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    console_handler.addFilter(SecretFilter())
    root.addHandler(console_handler)

    # These libraries log one line per HTTP request at INFO level.
    for noisy in ("urllib3", "httpx", "apscheduler", "requests"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
