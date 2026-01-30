"""Tautulli API client for retrieving watch history."""

import logging
from datetime import date, datetime
from typing import List, Optional

import requests

from src.models import Movie, WatchEntry, WatchlistEntry
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)


class TautulliSource(BaseSource):
    """Tautulli API client."""

    def __init__(self, base_url: str, api_key: str, user_id: int = 1):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()

    @property
    def name(self) -> str:
        return "Tautulli"

    def _get(self, cmd: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a request to Tautulli API."""
        url = f"{self.base_url}/api/v2"
        request_params = {
            "apikey": self.api_key,
            "cmd": cmd,
        }
        if params:
            request_params.update(params)

        try:
            response = self.session.get(url, params=request_params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get("response", {}).get("result") == "success":
                return data.get("response", {}).get("data")
            else:
                logger.error(f"Tautulli API error: {data}")
                return None

        except requests.RequestException as e:
            logger.error(f"Tautulli API error: {e}")
            return None

    def test_connection(self) -> bool:
        """Test Tautulli API connection."""
        data = self._get("get_server_info")
        if data:
            logger.info(f"Connected to Tautulli: {data.get('pms_name', 'Unknown')}")
            return True
        return False

    def get_watched(self) -> List[WatchEntry]:
        """Get watched movies from Tautulli history."""
        logger.info("Fetching watched movies from Tautulli...")

        entries = []
        seen_movies = set()  # Track unique movies

        # Get history with pagination
        start = 0
        length = 100  # Items per page

        while True:
            data = self._get("get_history", {
                "user_id": self.user_id,
                "media_type": "movie",
                "start": start,
                "length": length,
            })

            if not data:
                break

            history_data = data.get("data", [])
            if not history_data:
                break

            for item in history_data:
                # Skip if not a movie or not completed
                if item.get("media_type") != "movie":
                    continue

                title = item.get("title", "Unknown")
                year = item.get("year")

                # Create unique key for deduplication
                movie_key = (title.lower(), year)
                is_rewatch = movie_key in seen_movies
                seen_movies.add(movie_key)

                # Tautulli doesn't provide TMDB/IMDB IDs directly
                # These will need to be enriched via TMDB search
                movie = Movie(
                    title=title,
                    year=int(year) if year else None,
                )

                # Parse watched date
                watched_date = None
                stopped = item.get("stopped")
                if stopped:
                    try:
                        watched_date = datetime.fromtimestamp(stopped).date()
                    except (ValueError, TypeError):
                        pass

                # Tautulli doesn't have user ratings
                entry = WatchEntry(
                    movie=movie,
                    watched_date=watched_date,
                    rating=None,
                    rewatch=is_rewatch,
                )
                entries.append(entry)

            # Check if we've reached the end
            total_count = data.get("recordsFiltered", 0)
            start += length
            if start >= total_count:
                break

        # Keep only the most recent watch for each movie
        # (unless tracking rewatches is desired)
        unique_entries = self._deduplicate_entries(entries)

        logger.info(f"Found {len(unique_entries)} watched movies on Tautulli")
        return unique_entries

    def get_watchlist(self) -> List[WatchlistEntry]:
        """Tautulli doesn't have watchlist support."""
        logger.info("Tautulli does not support watchlists, returning empty list")
        return []

    def _deduplicate_entries(self, entries: List[WatchEntry]) -> List[WatchEntry]:
        """
        Deduplicate entries, keeping the most recent watch per movie.

        Marks earlier watches as rewatches.
        """
        # Group by movie
        movies: dict[tuple, List[WatchEntry]] = {}
        for entry in entries:
            key = (entry.movie.title.lower(), entry.movie.year)
            if key not in movies:
                movies[key] = []
            movies[key].append(entry)

        # For each movie, keep the most recent entry
        result = []
        for key, movie_entries in movies.items():
            # Sort by date, most recent first
            sorted_entries = sorted(
                movie_entries,
                key=lambda e: e.watched_date or date.min,
                reverse=True,
            )

            # Take the most recent
            latest = sorted_entries[0]

            # Mark as rewatch if there were multiple watches
            if len(sorted_entries) > 1:
                latest.rewatch = True

            result.append(latest)

        return result
