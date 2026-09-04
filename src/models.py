"""Data models shared by sources, storage and exporters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


def rating10_to_rating5(rating10: Optional[int]) -> Optional[float]:
    """Convert a 1-10 rating to the Letterboxd 0.5-5.0 scale.

    Only used for display and statistics: the CSV export always writes the
    integer ``Rating10`` column, never ``Rating``, because when both columns
    carry data Letterboxd silently keeps whichever comes second in the file.
    """
    if rating10 is None:
        return None
    return round(rating10 / 2.0 * 2) / 2


@dataclass
class Movie:
    """A film and the external identifiers known for it."""

    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    simkl_id: Optional[int] = None
    letterboxd_slug: Optional[str] = None
    directors: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable identity used to key export state.

        Preference order matches the Letterboxd importer's own matching order:
        an exact ID beats a title guess. Only fields that end up in the CSV are
        used, so the key can be rebuilt when a confirmed file is read back.
        """
        if self.tmdb_id:
            return f"tmdb:{self.tmdb_id}"
        if self.imdb_id:
            return f"imdb:{self.imdb_id}"
        return f"title:{self.title.strip().lower()}|{self.year or ''}"

    @property
    def has_exact_id(self) -> bool:
        """True when Letterboxd can match this film without guessing."""
        return bool(self.tmdb_id or self.imdb_id)

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Movie) and self.key == other.key


@dataclass
class WatchEntry:
    """One watched film, as it will appear on a CSV line."""

    movie: Movie
    watched_date: Optional[date] = None
    rating10: Optional[int] = None
    rewatch: bool = False
    tags: list[str] = field(default_factory=list)
    review: Optional[str] = None

    @property
    def rating5(self) -> Optional[float]:
        return rating10_to_rating5(self.rating10)

    @property
    def state_key(self) -> tuple[str, str]:
        """Key of the Letterboxd diary entry this line targets.

        The importer updates an existing diary entry when the film and the
        WatchedDate both match, so (film, date) is exactly the identity of an
        importable entry.
        """
        return self.movie.key, self.watched_date.isoformat() if self.watched_date else ""

    @property
    def fingerprint(self) -> str:
        """Hash of the user data carried by this entry.

        Only the mutable payload is hashed (rating, review, rewatch, tags), so
        that later metadata enrichment does not mark hundreds of unchanged
        entries as needing a re-import.
        """
        payload = json.dumps(
            {
                "rating10": self.rating10,
                "rewatch": bool(self.rewatch),
                "tags": normalize_tags(self.tags),
                "review": (self.review or "").strip(),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class WatchlistEntry:
    """One film on the watchlist."""

    movie: Movie
    added_date: Optional[date] = None


def normalize_tags(tags: Optional[list[str] | str]) -> list[str]:
    """Normalise tags to a clean list, from either a list or a CSV string."""
    if not tags:
        return []
    if isinstance(tags, str):
        parts = tags.split(",")
    else:
        parts = list(tags)
    return [part.strip() for part in parts if part and part.strip()]


def fingerprint_of(
    rating10: Optional[int],
    rewatch: bool,
    tags: Optional[list[str] | str],
    review: Optional[str],
) -> str:
    """Fingerprint from raw values, used when reading a CSV back in."""
    return WatchEntry(
        movie=Movie(title=""),
        rating10=rating10,
        rewatch=rewatch,
        tags=normalize_tags(tags),
        review=review,
    ).fingerprint
