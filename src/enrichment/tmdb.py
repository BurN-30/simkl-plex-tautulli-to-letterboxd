"""TMDB API client for movie enrichment and validation."""

import logging
import time
from typing import Optional

import requests

from src.models import Movie

logger = logging.getLogger(__name__)


class TMDBClient:
    """Client for The Movie Database API."""

    BASE_URL = "https://api.themoviedb.org/3"
    RATE_LIMIT_DELAY = 0.25  # 4 requests per second max

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a GET request to TMDB API."""
        self._rate_limit()

        url = f"{self.BASE_URL}{endpoint}"
        request_params = {"api_key": self.api_key}
        if params:
            request_params.update(params)

        try:
            response = self.session.get(url, params=request_params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"TMDB API error for {endpoint}: {e}")
            return None

    def get_movie_details(self, tmdb_id: int) -> Optional[dict]:
        """Get movie details including external IDs."""
        data = self._get(f"/movie/{tmdb_id}", {"append_to_response": "external_ids,credits"})
        return data

    def get_external_ids(self, tmdb_id: int) -> Optional[dict]:
        """Get external IDs (IMDB, etc.) for a movie."""
        data = self._get(f"/movie/{tmdb_id}/external_ids")
        return data

    def find_by_imdb_id(self, imdb_id: str) -> Optional[dict]:
        """Find movie by IMDB ID."""
        data = self._get(f"/find/{imdb_id}", {"external_source": "imdb_id"})
        if data and data.get("movie_results"):
            return data["movie_results"][0]
        return None

    def search_movie(self, title: str, year: Optional[int] = None) -> list[dict]:
        """Search for a movie by title and optionally year."""
        params = {"query": title}
        if year:
            params["year"] = str(year)

        data = self._get("/search/movie", params)
        if data:
            return data.get("results", [])
        return []

    def enrich_movie(self, movie: Movie) -> Movie:
        """
        Enrich a movie with TMDB and IMDB IDs.

        Strategy:
        1. If TMDB ID present -> get external IDs
        2. If IMDB ID present but no TMDB -> find by IMDB
        3. If no IDs -> search by title+year
        """
        enriched = Movie(
            title=movie.title,
            year=movie.year,
            tmdb_id=movie.tmdb_id,
            imdb_id=movie.imdb_id,
            directors=movie.directors.copy(),
        )

        # Strategy 1: We have TMDB ID
        if enriched.tmdb_id:
            details = self.get_movie_details(enriched.tmdb_id)
            if details:
                external_ids = details.get("external_ids", {})
                if not enriched.imdb_id and external_ids.get("imdb_id"):
                    enriched.imdb_id = external_ids["imdb_id"]

                # Get directors if not present
                if not enriched.directors:
                    credits = details.get("credits", {})
                    crew = credits.get("crew", [])
                    enriched.directors = [
                        p["name"] for p in crew if p.get("job") == "Director"
                    ]

                # Update year if not present
                if not enriched.year and details.get("release_date"):
                    try:
                        enriched.year = int(details["release_date"][:4])
                    except (ValueError, TypeError):
                        pass

                logger.debug(f"Enriched '{movie.title}' via TMDB ID {enriched.tmdb_id}")
                return enriched

        # Strategy 2: We have IMDB ID but no TMDB ID
        if enriched.imdb_id and not enriched.tmdb_id:
            result = self.find_by_imdb_id(enriched.imdb_id)
            if result:
                enriched.tmdb_id = result.get("id")
                if not enriched.year and result.get("release_date"):
                    try:
                        enriched.year = int(result["release_date"][:4])
                    except (ValueError, TypeError):
                        pass
                logger.debug(f"Found TMDB ID {enriched.tmdb_id} for IMDB {enriched.imdb_id}")

                # Now get full details including directors
                if enriched.tmdb_id:
                    details = self.get_movie_details(enriched.tmdb_id)
                    if details and not enriched.directors:
                        credits = details.get("credits", {})
                        crew = credits.get("crew", [])
                        enriched.directors = [
                            p["name"] for p in crew if p.get("job") == "Director"
                        ]
                return enriched

        # Strategy 3: Search by title and year
        if not enriched.tmdb_id and not enriched.imdb_id:
            results = self.search_movie(enriched.title, enriched.year)

            if results:
                # Take the first result if it's a good match
                best_match = self._find_best_match(results, enriched.title, enriched.year)
                if best_match:
                    enriched.tmdb_id = best_match.get("id")
                    if not enriched.year and best_match.get("release_date"):
                        try:
                            enriched.year = int(best_match["release_date"][:4])
                        except (ValueError, TypeError):
                            pass

                    # Get external IDs
                    if enriched.tmdb_id:
                        external_ids = self.get_external_ids(enriched.tmdb_id)
                        if external_ids and external_ids.get("imdb_id"):
                            enriched.imdb_id = external_ids["imdb_id"]

                        # Get directors
                        details = self.get_movie_details(enriched.tmdb_id)
                        if details and not enriched.directors:
                            credits = details.get("credits", {})
                            crew = credits.get("crew", [])
                            enriched.directors = [
                                p["name"] for p in crew if p.get("job") == "Director"
                            ]

                    logger.debug(f"Found '{movie.title}' via search: TMDB {enriched.tmdb_id}")
                    return enriched

            logger.warning(f"Could not find '{movie.title}' ({movie.year}) on TMDB")

        return enriched

    def _find_best_match(
        self, results: list[dict], title: str, year: Optional[int]
    ) -> Optional[dict]:
        """Find the best matching result from search results."""
        if not results:
            return None

        title_lower = title.lower()

        for result in results:
            result_title = result.get("title", "").lower()
            result_original_title = result.get("original_title", "").lower()
            result_year = None

            if result.get("release_date"):
                try:
                    result_year = int(result["release_date"][:4])
                except (ValueError, TypeError):
                    pass

            # Exact title match with year
            if year and result_year:
                if (result_title == title_lower or result_original_title == title_lower) and result_year == year:
                    return result

            # Exact title match without year constraint
            if result_title == title_lower or result_original_title == title_lower:
                return result

        # If no exact match, return the first result if year matches
        if year:
            for result in results:
                if result.get("release_date"):
                    try:
                        result_year = int(result["release_date"][:4])
                        if result_year == year:
                            return result
                    except (ValueError, TypeError):
                        pass

        # Return first result as fallback
        return results[0] if results else None

    def validate_movie(self, movie: Movie) -> bool:
        """Check if a movie has valid IDs."""
        return bool(movie.tmdb_id or movie.imdb_id)
