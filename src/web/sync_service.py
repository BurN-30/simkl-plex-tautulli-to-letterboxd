"""Optional background sync for the dashboard.

The weekly Windows scheduled task is the normal way to refresh data; this
scheduler only exists so the dashboard can stay current while it is open. It is
disabled when ``SYNC_INTERVAL`` is 0.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from src.sync import build_source, sync_to_database
from src.web.database import Database

logger = logging.getLogger(__name__)


class SyncService:
    """Runs :func:`src.sync.sync_to_database` on a timer and on demand."""

    def __init__(self, database: Database, on_sync_complete: Optional[Callable] = None):
        self.db = database
        self.on_sync_complete = on_sync_complete
        self.scheduler = BackgroundScheduler()
        self._is_syncing = False

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing

    def start(self, interval_minutes: int = 0) -> None:
        if interval_minutes <= 0:
            logger.info("Background sync disabled (SYNC_INTERVAL=0)")
            return
        self.scheduler.add_job(
            self.sync,
            "interval",
            minutes=interval_minutes,
            id="sync_source",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("Background sync started (every %d min)", interval_minutes)

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Background sync stopped")

    def sync(self) -> dict:
        if self._is_syncing:
            logger.warning("Sync already running, skipping")
            return {"status": "skipped", "reason": "already syncing"}

        self._is_syncing = True
        try:
            result = sync_to_database(self.db, build_source())
            if self.on_sync_complete:
                self.on_sync_complete(result)
            return result
        finally:
            self._is_syncing = False
