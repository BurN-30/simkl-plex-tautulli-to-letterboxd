"""Main entry point for Letterboxd Sync Tool."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from src.config import Config
from src.enrichment.tmdb import TMDBClient
from src.exporters.letterboxd import LetterboxdExporter
from src.models import WatchEntry, WatchlistEntry
from src.sources.base import BaseSource
from src.sources.plex import PlexSource
from src.sources.simkl import SimklSource
from src.sources.tautulli import TautulliSource


def setup_logging(level: str) -> None:
    """Configure logging."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"sync_{datetime.now().strftime('%Y-%m-%d')}.log"

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def get_source(source_name: str) -> BaseSource:
    """Create and return the appropriate source."""
    if source_name == "simkl":
        return SimklSource(
            client_id=Config.SIMKL_CLIENT_ID,
            token_file=Config.SIMKL_TOKEN_FILE,
        )
    elif source_name == "plex":
        return PlexSource(
            base_url=Config.PLEX_URL,
            token=Config.PLEX_TOKEN,
        )
    elif source_name == "tautulli":
        return TautulliSource(
            base_url=Config.TAUTULLI_URL,
            api_key=Config.TAUTULLI_API_KEY,
            user_id=Config.TAUTULLI_USER_ID,
        )
    else:
        raise ValueError(f"Unknown source: {source_name}")


def enrich_entries(
    entries: List[WatchEntry] | List[WatchlistEntry],
    tmdb_client: TMDBClient,
    logger: logging.Logger,
) -> None:
    """Enrich movie entries with TMDB data."""
    total = len(entries)
    for i, entry in enumerate(entries, 1):
        if i % 10 == 0 or i == total:
            logger.info(f"Enriching movies: {i}/{total}")

        entry.movie = tmdb_client.enrich_movie(entry.movie)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Export watch history to Letterboxd CSV format"
    )
    parser.add_argument(
        "--source",
        choices=["simkl", "plex", "tautulli"],
        default=None,
        help="Data source (default: from .env)",
    )
    parser.add_argument(
        "--no-watchlist",
        action="store_true",
        help="Skip watchlist export",
    )
    parser.add_argument(
        "--no-watched",
        action="store_true",
        help="Skip watched history export",
    )
    args = parser.parse_args()

    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease check your .env file")
        return 1

    # Setup
    Config.ensure_directories()
    setup_logging(Config.LOG_LEVEL)
    logger = logging.getLogger(__name__)

    logger.info("=" * 50)
    logger.info("Letterboxd Sync Tool")
    logger.info("=" * 50)

    # Determine source
    source_name = args.source or Config.PRIMARY_SOURCE
    logger.info(f"Using source: {source_name}")

    # Create components
    try:
        source = get_source(source_name)
    except ValueError as e:
        logger.error(str(e))
        return 1

    # Test connection
    if not source.test_connection():
        logger.error(f"Failed to connect to {source.name}")
        return 1

    tmdb_client = TMDBClient(Config.TMDB_API_KEY)
    exporter = LetterboxdExporter(Config.OUTPUT_DIR)

    # Export watched movies
    export_watched = Config.EXPORT_WATCHED and not args.no_watched
    if export_watched:
        logger.info("")
        logger.info("Fetching watched movies...")
        watched = source.get_watched()

        if watched:
            logger.info(f"Enriching {len(watched)} watched movies with TMDB data...")
            enrich_entries(watched, tmdb_client, logger)

            output_file = exporter.export_watched(watched)
            logger.info(f"Watched movies exported to: {output_file}")
        else:
            logger.warning("No watched movies found")

    # Export watchlist
    export_watchlist = Config.EXPORT_WATCHLIST and not args.no_watchlist
    if export_watchlist:
        logger.info("")
        logger.info("Fetching watchlist...")
        watchlist = source.get_watchlist()

        if watchlist:
            logger.info(f"Enriching {len(watchlist)} watchlist movies with TMDB data...")
            enrich_entries(watchlist, tmdb_client, logger)

            output_file = exporter.export_watchlist(watchlist)
            logger.info(f"Watchlist exported to: {output_file}")
        else:
            logger.info("No watchlist items found")

    logger.info("")
    logger.info("=" * 50)
    logger.info("Sync complete!")
    logger.info(f"Output files are in: {Config.OUTPUT_DIR}")
    logger.info("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
