"""Simkl API client: completed films, ratings and watchlist.

The API requires both an ``Authorization: Bearer`` header and the
``simkl-api-key`` header carrying the client id; sending only one of them
returns HTTP 412.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Iterable, List, Optional

import requests

from src.auth.simkl_oauth import SimklOAuth
from src.models import Movie, WatchEntry, WatchlistEntry
from src.sources.base import BaseSource
from src.timeutils import to_calendar_date

logger = logging.getLogger(__name__)


def _as_items(payload: Any) -> list[dict]:
    """Normalise a Simkl response into a list of items.

    ``/sync/all-items`` returns ``{"movies": [...]}``, but a filtered endpoint
    can return a bare list, and an empty account returns ``None``.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        movies = payload.get("movies")
        if isinstance(movies, list):
            return [item for item in movies if isinstance(item, dict)]
    return []


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_movie(payload: dict) -> Movie:
    """Build a :class:`Movie` from the ``movie`` object of a Simkl item."""
    ids = payload.get("ids") or {}
    return Movie(
        title=(payload.get("title") or "").strip() or "Unknown",
        year=_int_or_none(payload.get("year")),
        tmdb_id=_int_or_none(ids.get("tmdb")),
        imdb_id=(ids.get("imdb") or None),
        simkl_id=_int_or_none(ids.get("simkl")),
        letterboxd_slug=(ids.get("letterboxd") or None),
    )


def parse_watch_entry(item: dict, timezone_name: Optional[str] = None) -> Optional[WatchEntry]:
    """Build a :class:`WatchEntry` from one ``/sync/all-items`` item."""
    movie_payload = item.get("movie")
    if not isinstance(movie_payload, dict):
        return None

    rating10 = _int_or_none(item.get("user_rating"))
    if rating10 is not None and not 1 <= rating10 <= 10:
        logger.warning("Ignoring out-of-range Simkl rating %r", rating10)
        rating10 = None

    return WatchEntry(
        movie=parse_movie(movie_payload),
        watched_date=to_calendar_date(item.get("last_watched_at"), timezone_name),
        rating10=rating10,
        # Simkl has no rewatch concept; the flag stays editable in the dashboard.
        rewatch=False,
    )


def parse_watchlist_entry(item: dict) -> Optional[WatchlistEntry]:
    movie_payload = item.get("movie")
    if not isinstance(movie_payload, dict):
        return None
    return WatchlistEntry(
        movie=parse_movie(movie_payload),
        added_date=to_calendar_date(item.get("added_to_watchlist_at")),
    )


def merge_ratings(entries: Iterable[WatchEntry], rating_items: Iterable[dict]) -> int:
    """Apply the ratings list onto watched entries, keyed by Simkl id.

    ``/sync/all-items/movies/completed`` already carries ``user_rating``, but
    the dedicated ratings list is the authoritative one and also covers films
    rated after the watch was logged. Returns the number of entries updated.
    """
    ratings: dict[int, int] = {}
    for item in rating_items:
        movie_payload = item.get("movie")
        if not isinstance(movie_payload, dict):
            continue
        simkl_id = _int_or_none((movie_payload.get("ids") or {}).get("simkl"))
        rating10 = _int_or_none(item.get("user_rating"))
        if simkl_id and rating10 and 1 <= rating10 <= 10:
            ratings[simkl_id] = rating10

    updated = 0
    for entry in entries:
        simkl_id = entry.movie.simkl_id
        if simkl_id and simkl_id in ratings and entry.rating10 != ratings[simkl_id]:
            entry.rating10 = ratings[simkl_id]
            updated += 1
    return updated


class SimklSource(BaseSource):
    """Read-only Simkl client."""

    BASE_URL = "https://api.simkl.com"
    RETRIES = 3
    RETRY_DELAY = 3.0

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_file: Path,
        port: int = 19877,
        timezone_name: Optional[str] = None,
    ):
        self.client_id = client_id
        self.timezone_name = timezone_name
        self.oauth = SimklOAuth(client_id, client_secret, token_file, port=port)
        self.session = requests.Session()
        self._access_token: Optional[str] = None
        self._last_rating_items: list[dict] = []

    @property
    def name(self) -> str:
        return "Simkl"

    def _ensure_authenticated(self) -> bool:
        if self._access_token:
            return True
        token = self.oauth.access_token
        if token:
            self._access_token = token
            return True
        logger.error(
            "No Simkl access token. Run the dashboard (`serve`) to authorise, "
            "or place the token in %s",
            self.oauth.token_file,
        )
        return False

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """Authenticated GET with a short retry on transient failures."""
        if not self._ensure_authenticated():
            return None

        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "simkl-api-key": self.client_id,
            "Accept": "application/json",
        }

        for attempt in range(1, self.RETRIES + 1):
            try:
                response = self.session.get(url, headers=headers, params=params, timeout=60)
                if response.status_code in (401, 403, 412):
                    logger.error(
                        "Simkl refused the request on %s (HTTP %d). The token or "
                        "the client id is invalid.",
                        endpoint,
                        response.status_code,
                    )
                    return None
                response.raise_for_status()
                if not response.content:
                    return None
                return response.json()
            except requests.RequestException as exc:
                if attempt == self.RETRIES:
                    logger.error("Simkl request failed on %s: %s", endpoint, exc)
                    return None
                logger.warning(
                    "Simkl request failed on %s (attempt %d/%d): %s",
                    endpoint,
                    attempt,
                    self.RETRIES,
                    exc,
                )
                time.sleep(self.RETRY_DELAY * attempt)
        return None

    def test_connection(self) -> bool:
        if not self._ensure_authenticated():
            return False
        settings = self._get("/users/settings")
        if not settings:
            return False
        user = (settings.get("user") or {}) if isinstance(settings, dict) else {}
        logger.info("Connected to Simkl as %s", user.get("name") or "unknown user")
        return True

    def get_watched(self) -> List[WatchEntry]:
        """Completed films, with ratings merged in."""
        logger.info("Fetching completed films from Simkl...")
        completed = _as_items(
            self._get("/sync/all-items/movies/completed", {"extended": "full"})
        )
        logger.info("Simkl returned %d completed films", len(completed))

        entries: list[WatchEntry] = []
        for item in completed:
            entry = parse_watch_entry(item, self.timezone_name)
            if entry is not None:
                entries.append(entry)

        rating_items = _as_items(self._get("/sync/all-items/movies", {"extended": "full"}))
        self._last_rating_items = rating_items
        if rating_items:
            updated = merge_ratings(entries, rating_items)
            logger.info("Merged ratings from Simkl (%d entries updated)", updated)

        missing_ids = sum(1 for entry in entries if not entry.movie.has_exact_id)
        if missing_ids:
            logger.warning("%d films have no TMDB or IMDb id and will be matched by title", missing_ids)

        return entries

    def get_watchlist(self) -> List[WatchlistEntry]:
        logger.info("Fetching Simkl watchlist (plantowatch)...")
        items = _as_items(
            self._get("/sync/all-items/movies/plantowatch", {"extended": "full"})
        )
        entries: list[WatchlistEntry] = []
        for item in items:
            entry = parse_watchlist_entry(item)
            if entry is not None:
                entries.append(entry)
        logger.info("Simkl returned %d watchlist films", len(entries))
        return entries
