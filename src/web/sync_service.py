"""Background sync service to monitor Simkl for changes."""

import logging
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from src.config import Config
from src.enrichment.tmdb import TMDBClient
from src.web.database import Database

logger = logging.getLogger(__name__)


class SyncService:
    """Background service to sync movies from the configured source."""

    def __init__(
        self,
        database: Database,
        on_sync_complete: Optional[Callable] = None,
    ):
        self.db = database
        self.on_sync_complete = on_sync_complete
        self.scheduler = BackgroundScheduler()
        self._is_syncing = False

        # Initialize clients
        self.source = self._create_source()
        self.tmdb = TMDBClient(Config.TMDB_API_KEY)

    def _create_source(self):
        """Create the appropriate data source based on PRIMARY_SOURCE config."""
        name = Config.PRIMARY_SOURCE
        if name == "simkl":
            from src.sources.simkl import SimklSource
            return SimklSource(
                client_id=Config.SIMKL_CLIENT_ID,
                client_secret=Config.SIMKL_CLIENT_SECRET,
                token_file=Config.SIMKL_TOKEN_FILE,
                port=Config.OAUTH_PORT,
            )
        elif name == "plex":
            from src.sources.plex import PlexSource
            return PlexSource(
                base_url=Config.PLEX_URL,
                token=Config.PLEX_TOKEN,
            )
        elif name == "tautulli":
            from src.sources.tautulli import TautulliSource
            return TautulliSource(
                base_url=Config.TAUTULLI_URL,
                api_key=Config.TAUTULLI_API_KEY,
                user_id=Config.TAUTULLI_USER_ID,
            )
        else:
            raise ValueError(f"Unknown source: {name}")

    def start(self, interval_minutes: int = 15) -> None:
        """Start the background sync scheduler."""
        # Run sync job every N minutes
        self.scheduler.add_job(
            self.sync,
            "interval",
            minutes=interval_minutes,
            id="sync_simkl",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(f"Sync service started (interval: {interval_minutes} min)")

    def stop(self) -> None:
        """Stop the sync scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Sync service stopped")

    def sync(self) -> dict:
        """Perform a full sync with Simkl."""
        if self._is_syncing:
            logger.warning("Sync already in progress, skipping")
            return {"status": "skipped", "reason": "already syncing"}

        self._is_syncing = True
        self.db.update_sync_status(status="syncing", error_message=None)

        try:
            logger.info(f"Starting sync from {self.source.name}...")

            # Test connection
            if not self.source.test_connection():
                raise Exception(f"Failed to connect to {self.source.name}")

            # Get watched movies
            watched_entries = self.source.get_watched()
            logger.info(f"Fetched {len(watched_entries)} watched movies")

            # Get watchlist
            watchlist_entries = self.source.get_watchlist()
            logger.info(f"Fetched {len(watchlist_entries)} watchlist movies")

            # Process watched movies
            watched_count = 0
            for entry in watched_entries:
                # Enrich with TMDB
                entry.movie = self.tmdb.enrich_movie(entry.movie)

                # Get poster URL
                poster_url = None
                if entry.movie.tmdb_id:
                    details = self.tmdb.get_movie_details(entry.movie.tmdb_id)
                    if details and details.get("poster_path"):
                        poster_url = f"https://image.tmdb.org/t/p/w300{details['poster_path']}"

                # Upsert to database
                movie_data = {
                    "tmdb_id": entry.movie.tmdb_id,
                    "imdb_id": entry.movie.imdb_id,
                    "title": entry.movie.title,
                    "year": entry.movie.year,
                    "directors": ", ".join(entry.movie.directors) if entry.movie.directors else None,
                    "poster_url": poster_url,
                    "watched_date": entry.watched_date,
                    "rating": entry.rating,
                    "rewatch": entry.rewatch,
                    "is_watched": True,
                    "is_watchlist": False,
                    "source": Config.PRIMARY_SOURCE,
                }
                self.db.upsert_movie(movie_data)
                watched_count += 1

            # Process watchlist
            watchlist_count = 0
            for entry in watchlist_entries:
                # Enrich with TMDB
                entry.movie = self.tmdb.enrich_movie(entry.movie)

                # Get poster URL
                poster_url = None
                if entry.movie.tmdb_id:
                    details = self.tmdb.get_movie_details(entry.movie.tmdb_id)
                    if details and details.get("poster_path"):
                        poster_url = f"https://image.tmdb.org/t/p/w300{details['poster_path']}"

                movie_data = {
                    "tmdb_id": entry.movie.tmdb_id,
                    "imdb_id": entry.movie.imdb_id,
                    "title": entry.movie.title,
                    "year": entry.movie.year,
                    "directors": ", ".join(entry.movie.directors) if entry.movie.directors else None,
                    "poster_url": poster_url,
                    "is_watched": False,
                    "is_watchlist": True,
                    "source": Config.PRIMARY_SOURCE,
                }
                self.db.upsert_movie(movie_data)
                watchlist_count += 1

            # Update sync status
            self.db.update_sync_status(
                last_sync=datetime.utcnow(),
                movies_count=watched_count,
                watchlist_count=watchlist_count,
                status="idle",
            )

            logger.info(f"Sync complete: {watched_count} watched, {watchlist_count} watchlist")

            result = {
                "status": "success",
                "watched_count": watched_count,
                "watchlist_count": watchlist_count,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if self.on_sync_complete:
                self.on_sync_complete(result)

            return result

        except Exception as e:
            logger.error(f"Sync error: {e}")
            self.db.update_sync_status(
                status="error",
                error_message=str(e),
            )
            return {"status": "error", "error": str(e)}

        finally:
            self._is_syncing = False

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing
