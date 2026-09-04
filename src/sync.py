"""Pull a source into the local database.

The database is the single source of truth for the exporter: sources fill in
the film metadata, ratings and watch dates, while reviews, tags and the rewatch
flag are typed in the dashboard and never overwritten by a sync.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.config import Config
from src.models import WatchEntry, WatchlistEntry, rating10_to_rating5
from src.sources.base import BaseSource
from src.web.database import Database, utcnow

logger = logging.getLogger(__name__)


def build_source(name: Optional[str] = None) -> BaseSource:
    """Instantiate the configured source."""
    name = (name or Config.PRIMARY_SOURCE).lower()

    if name == "simkl":
        from src.sources.simkl import SimklSource

        return SimklSource(
            client_id=Config.SIMKL_CLIENT_ID,
            client_secret=Config.SIMKL_CLIENT_SECRET,
            token_file=Config.SIMKL_TOKEN_FILE,
            port=Config.OAUTH_PORT,
            timezone_name=Config.LOCAL_TIMEZONE if Config.SIMKL_CONVERT_TIMEZONE else None,
        )

    if name == "plex":
        from src.sources.plex import PlexSource

        return PlexSource(
            base_url=Config.PLEX_URL,
            token=Config.PLEX_TOKEN,
            timezone_name=Config.LOCAL_TIMEZONE,
        )

    if name == "tautulli":
        from src.sources.tautulli import TautulliSource

        return TautulliSource(
            base_url=Config.TAUTULLI_URL,
            api_key=Config.TAUTULLI_API_KEY,
            user_id=Config.TAUTULLI_USER_ID,
            timezone_name=Config.LOCAL_TIMEZONE,
        )

    raise ValueError(f"Unknown source: {name}")


def _watched_payload(entry: WatchEntry, source_name: str) -> dict:
    movie = entry.movie
    return {
        "tmdb_id": movie.tmdb_id,
        "imdb_id": movie.imdb_id,
        "simkl_id": movie.simkl_id,
        "letterboxd_slug": movie.letterboxd_slug,
        "title": movie.title,
        "year": movie.year,
        "directors": ", ".join(movie.directors) if movie.directors else None,
        "watched_date": entry.watched_date,
        "rating10": entry.rating10,
        "rating": rating10_to_rating5(entry.rating10),
        "is_watched": True,
        "is_watchlist": False,
        "source": source_name,
    }


def _watchlist_payload(entry: WatchlistEntry, source_name: str) -> dict:
    movie = entry.movie
    return {
        "tmdb_id": movie.tmdb_id,
        "imdb_id": movie.imdb_id,
        "simkl_id": movie.simkl_id,
        "letterboxd_slug": movie.letterboxd_slug,
        "title": movie.title,
        "year": movie.year,
        "directors": ", ".join(movie.directors) if movie.directors else None,
        "is_watched": False,
        "is_watchlist": True,
        "source": source_name,
    }


def enrich_with_tmdb(entries, logger_: logging.Logger) -> None:
    """Fill in missing ids, directors and posters when a TMDB key is set."""
    if not Config.tmdb_enabled():
        return
    from src.enrichment.tmdb import TMDBClient

    client = TMDBClient(Config.TMDB_API_KEY)
    total = len(entries)
    for index, entry in enumerate(entries, start=1):
        entry.movie = client.enrich_movie(entry.movie)
        if index % 50 == 0 or index == total:
            logger_.info("TMDB enrichment: %d/%d", index, total)


def sync_to_database(
    database: Database,
    source: Optional[BaseSource] = None,
    include_watchlist: bool = True,
) -> dict:
    """Fetch a source and write it into the database. Returns a summary."""
    source = source or build_source()
    logger.info("Syncing from %s", source.name)
    database.update_sync_status(status="syncing", error_message=None)

    try:
        if not source.test_connection():
            raise RuntimeError(f"Cannot reach {source.name}")

        watched = source.get_watched()
        enrich_with_tmdb(watched, logger)
        for entry in watched:
            database.upsert_movie(_watched_payload(entry, source.name.lower()))

        watchlist: list[WatchlistEntry] = []
        if include_watchlist:
            watchlist = source.get_watchlist()
            enrich_with_tmdb(watchlist, logger)
            for entry in watchlist:
                database.upsert_movie(_watchlist_payload(entry, source.name.lower()))

        database.update_sync_status(
            last_sync=utcnow(),
            movies_count=len(watched),
            watchlist_count=len(watchlist),
            status="idle",
        )
        logger.info(
            "Sync complete: %d watched, %d watchlist", len(watched), len(watchlist)
        )
        return {
            "status": "success",
            "watched": len(watched),
            "watchlist": len(watchlist),
            "source": source.name,
        }

    except Exception as exc:
        logger.error("Sync failed: %s", exc)
        database.update_sync_status(status="error", error_message=str(exc))
        return {"status": "error", "error": str(exc), "source": source.name}
