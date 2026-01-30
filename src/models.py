"""Data models for the Letterboxd Sync Tool."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Movie:
    """Represents a movie with its metadata."""

    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    directors: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        """Hash based on TMDB ID, IMDB ID, or title+year."""
        if self.tmdb_id:
            return hash(("tmdb", self.tmdb_id))
        if self.imdb_id:
            return hash(("imdb", self.imdb_id))
        return hash((self.title.lower(), self.year))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Movie):
            return False
        if self.tmdb_id and other.tmdb_id:
            return self.tmdb_id == other.tmdb_id
        if self.imdb_id and other.imdb_id:
            return self.imdb_id == other.imdb_id
        return self.title.lower() == other.title.lower() and self.year == other.year


@dataclass
class WatchEntry:
    """Represents a watched movie entry."""

    movie: Movie
    watched_date: Optional[date] = None
    rating: Optional[float] = None  # Scale 0.5-5.0
    rewatch: bool = False
    tags: list[str] = field(default_factory=list)
    review: Optional[str] = None

    @classmethod
    def convert_rating_10_to_5(cls, rating_10: float) -> float:
        """Convert a 1-10 rating to 0.5-5.0 scale."""
        # Map 1-10 to 0.5-5.0 (round to nearest 0.5)
        rating_5 = rating_10 / 2.0
        return round(rating_5 * 2) / 2  # Round to nearest 0.5


@dataclass
class WatchlistEntry:
    """Represents a watchlist entry."""

    movie: Movie
    added_date: Optional[date] = None
    priority: Optional[int] = None  # Optional priority/ranking
