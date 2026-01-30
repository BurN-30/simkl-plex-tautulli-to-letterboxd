"""Plex API client for retrieving watch history."""

import logging
import re
from datetime import date, datetime
from typing import List, Optional

from src.models import Movie, WatchEntry, WatchlistEntry
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)


class PlexSource(BaseSource):
    """Plex API client using python-plexapi."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._server = None

    @property
    def name(self) -> str:
        return "Plex"

    def _get_server(self):
        """Get or create Plex server connection."""
        if self._server is None:
            try:
                from plexapi.server import PlexServer
                self._server = PlexServer(self.base_url, self.token)
            except Exception as e:
                logger.error(f"Failed to connect to Plex: {e}")
                raise
        return self._server

    def test_connection(self) -> bool:
        """Test Plex connection."""
        try:
            server = self._get_server()
            logger.info(f"Connected to Plex server: {server.friendlyName}")
            return True
        except Exception as e:
            logger.error(f"Plex connection failed: {e}")
            return False

    def get_watched(self) -> List[WatchEntry]:
        """Get watched movies from Plex."""
        logger.info("Fetching watched movies from Plex...")

        try:
            server = self._get_server()
        except Exception:
            return []

        entries = []

        # Get all movie libraries
        for section in server.library.sections():
            if section.type != "movie":
                continue

            logger.debug(f"Scanning library: {section.title}")

            # Get all watched movies in this library
            for item in section.search(unwatched=False):
                if not item.isWatched:
                    continue

                movie = self._parse_movie(item)
                if not movie:
                    continue

                # Get watch date
                watched_date = None
                if item.lastViewedAt:
                    watched_date = item.lastViewedAt.date()

                # Get rating (Plex uses 1-10 scale)
                rating = None
                if item.userRating:
                    rating = WatchEntry.convert_rating_10_to_5(item.userRating)

                entry = WatchEntry(
                    movie=movie,
                    watched_date=watched_date,
                    rating=rating,
                    rewatch=item.viewCount > 1 if item.viewCount else False,
                )
                entries.append(entry)

        logger.info(f"Found {len(entries)} watched movies on Plex")
        return entries

    def get_watchlist(self) -> List[WatchlistEntry]:
        """Get watchlist from Plex (not typically available)."""
        logger.info("Plex watchlist not supported, returning empty list")
        return []

    def _parse_movie(self, item) -> Optional[Movie]:
        """Parse a Plex movie item into a Movie object."""
        try:
            title = item.title
            year = item.year

            # Extract IDs from guids
            tmdb_id = None
            imdb_id = None

            for guid in getattr(item, "guids", []):
                guid_str = str(guid.id)
                if guid_str.startswith("tmdb://"):
                    try:
                        tmdb_id = int(guid_str.replace("tmdb://", ""))
                    except ValueError:
                        pass
                elif guid_str.startswith("imdb://"):
                    imdb_id = guid_str.replace("imdb://", "")

            # Also check the main guid for older Plex versions
            if hasattr(item, "guid"):
                main_guid = str(item.guid)
                if "themoviedb://" in main_guid:
                    match = re.search(r"themoviedb://(\d+)", main_guid)
                    if match:
                        tmdb_id = int(match.group(1))
                elif "imdb://" in main_guid:
                    match = re.search(r"imdb://(tt\d+)", main_guid)
                    if match:
                        imdb_id = match.group(1)

            # Get directors
            directors = []
            for director in getattr(item, "directors", []):
                directors.append(director.tag)

            return Movie(
                title=title,
                year=year,
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
                directors=directors,
            )

        except Exception as e:
            logger.warning(f"Failed to parse Plex movie: {e}")
            return None
