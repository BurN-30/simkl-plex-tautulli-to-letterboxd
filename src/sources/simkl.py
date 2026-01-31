"""Simkl API client for retrieving watch history."""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import requests

from src.auth.simkl_oauth import SimklOAuth
from src.models import Movie, WatchEntry, WatchlistEntry
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)


class SimklSource(BaseSource):
    """Simkl API client."""

    BASE_URL = "https://api.simkl.com"

    def __init__(self, client_id: str, token_file: Path, port: int = 19877):
        self.client_id = client_id
        self.oauth = SimklOAuth(client_id, token_file, port=port)
        self.session = requests.Session()
        self._access_token: Optional[str] = None

    @property
    def name(self) -> str:
        return "Simkl"

    def _ensure_authenticated(self) -> bool:
        """Ensure we have a valid access token."""
        if self._access_token:
            return True

        token = self.oauth.authenticate()
        if token:
            self._access_token = token
            return True

        logger.error("Failed to authenticate with Simkl")
        return False

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict | list]:
        """Make authenticated GET request to Simkl API."""
        if not self._ensure_authenticated():
            return None

        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "simkl-api-key": self.client_id,
            "Content-Type": "application/json",
        }

        try:
            response = self.session.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Simkl API error for {endpoint}: {e}")
            return None

    def test_connection(self) -> bool:
        """Test Simkl API connection."""
        if not self._ensure_authenticated():
            return False

        result = self._get("/users/settings")
        return result is not None

    def get_watched(self) -> List[WatchEntry]:
        """Get watched movies from Simkl."""
        logger.info("Fetching watched movies from Simkl...")

        # Get all movies with their status
        data = self._get("/sync/all-items/movies")
        if not data:
            return []

        entries = []
        movies_data = data.get("movies", [])

        for item in movies_data:
            movie_data = item.get("movie", {})

            # Extract IDs
            ids = movie_data.get("ids", {})
            tmdb_id = ids.get("tmdb")
            imdb_id = ids.get("imdb")

            # Create movie object
            movie = Movie(
                title=movie_data.get("title", "Unknown"),
                year=movie_data.get("year"),
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
            )

            # Parse watched date
            watched_date = None
            last_watched = item.get("last_watched_at") or item.get("watched_at")
            if last_watched:
                try:
                    dt = datetime.fromisoformat(last_watched.replace("Z", "+00:00"))
                    watched_date = dt.date()
                except ValueError:
                    pass

            # Parse rating (Simkl uses 1-10 scale)
            rating = None
            user_rating = item.get("user_rating")
            if user_rating:
                rating = WatchEntry.convert_rating_10_to_5(float(user_rating))

            entry = WatchEntry(
                movie=movie,
                watched_date=watched_date,
                rating=rating,
                rewatch=False,  # Simkl doesn't track rewatches explicitly
            )
            entries.append(entry)

        logger.info(f"Found {len(entries)} watched movies on Simkl")
        return entries

    def get_watchlist(self) -> List[WatchlistEntry]:
        """Get watchlist from Simkl."""
        logger.info("Fetching watchlist from Simkl...")

        # Get plantowatch items
        data = self._get("/sync/all-items/movies/plantowatch")
        if not data:
            return []

        entries = []
        movies_data = data.get("movies", [])

        for item in movies_data:
            movie_data = item.get("movie", {})

            # Extract IDs
            ids = movie_data.get("ids", {})
            tmdb_id = ids.get("tmdb")
            imdb_id = ids.get("imdb")

            movie = Movie(
                title=movie_data.get("title", "Unknown"),
                year=movie_data.get("year"),
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
            )

            # Parse added date
            added_date = None
            added_at = item.get("added_at")
            if added_at:
                try:
                    dt = datetime.fromisoformat(added_at.replace("Z", "+00:00"))
                    added_date = dt.date()
                except ValueError:
                    pass

            entry = WatchlistEntry(
                movie=movie,
                added_date=added_date,
            )
            entries.append(entry)

        logger.info(f"Found {len(entries)} movies in Simkl watchlist")
        return entries
