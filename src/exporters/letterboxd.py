"""Build the CSV files that are handed to letterboxd.com/import."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence

from src.letterboxd import csv_format
from src.models import Movie, WatchEntry, WatchlistEntry, fingerprint_of, normalize_tags

logger = logging.getLogger(__name__)

#: Column layout for an import to the profile / diary.
#:
#: ``Rating10`` is used and ``Rating`` is deliberately absent: Letterboxd states
#: that when both columns carry data, "whichever column appears second in the
#: file will take precedence", so shipping only one removes the ambiguity.
WATCHED_HEADERS: tuple[str, ...] = (
    "tmdbID",
    "imdbID",
    "Title",
    "Year",
    "Directors",
    "WatchedDate",
    "Rating10",
    "Rewatch",
    "Tags",
    "Review",
)

#: Column layout for an import to the watchlist.
WATCHLIST_HEADERS: tuple[str, ...] = ("Title", "Year", "tmdbID", "imdbID")


@dataclass
class ExportResult:
    """Outcome of one export run."""

    kind: str
    files: list[Path] = field(default_factory=list)
    rows: int = 0
    skipped_unchanged: int = 0
    skipped_no_id: int = 0

    @property
    def total_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.files if path.exists())


def watched_row(entry: WatchEntry) -> list[str]:
    """Render one watched entry as CSV values."""
    movie = entry.movie
    return [
        str(movie.tmdb_id) if movie.tmdb_id else "",
        movie.imdb_id or "",
        movie.title,
        str(movie.year) if movie.year else "",
        ", ".join(movie.directors) if movie.directors else "",
        entry.watched_date.isoformat() if entry.watched_date else "",
        str(entry.rating10) if entry.rating10 else "",
        "true" if entry.rewatch else "false",
        ", ".join(normalize_tags(entry.tags)),
        entry.review or "",
    ]


def watchlist_row(entry: WatchlistEntry) -> list[str]:
    """Render one watchlist entry as CSV values."""
    movie = entry.movie
    return [
        movie.title,
        str(movie.year) if movie.year else "",
        str(movie.tmdb_id) if movie.tmdb_id else "",
        movie.imdb_id or "",
    ]


def select_pending(
    entries: Iterable[WatchEntry],
    state: dict[tuple[str, str], str],
) -> tuple[list[WatchEntry], int]:
    """Split entries into those needing an import and those already confirmed.

    An entry is pending when its (film, WatchedDate) pair has never been
    confirmed, or when its user data changed since the last confirmation.
    """
    pending: list[WatchEntry] = []
    unchanged = 0
    for entry in entries:
        confirmed = state.get(entry.state_key)
        if confirmed is not None and confirmed == entry.fingerprint:
            unchanged += 1
        else:
            pending.append(entry)
    return pending, unchanged


def _timestamp(moment: Optional[datetime] = None) -> str:
    return (moment or datetime.now()).strftime("%Y%m%d-%H%M%S")


class LetterboxdExporter:
    """Write import-ready CSV files into the pending directory."""

    def __init__(self, pending_dir: Path, max_bytes: int = csv_format.DEFAULT_MAX_FILE_BYTES):
        self.pending_dir = Path(pending_dir)
        self.max_bytes = max_bytes

    def export_watched(
        self,
        entries: Sequence[WatchEntry],
        state: Optional[dict[tuple[str, str], str]] = None,
        moment: Optional[datetime] = None,
    ) -> ExportResult:
        """Export watched films, optionally filtered against the export state."""
        result = ExportResult(kind="watched")

        if state is None:
            candidates = list(entries)
        else:
            candidates, result.skipped_unchanged = select_pending(entries, state)

        exportable: list[WatchEntry] = []
        for entry in candidates:
            if entry.movie.has_exact_id or entry.movie.title.strip():
                exportable.append(entry)
            else:
                result.skipped_no_id += 1

        no_id = sum(1 for entry in exportable if not entry.movie.has_exact_id)
        if no_id:
            logger.warning(
                "%d exported films have no TMDB or IMDb id; Letterboxd will "
                "best-guess them from title and year, check them on the "
                "confirmation screen",
                no_id,
            )

        if not exportable:
            logger.info("Nothing to export for watched films")
            return result

        result.files = csv_format.write_chunked(
            self.pending_dir,
            f"letterboxd_watched_{_timestamp(moment)}",
            WATCHED_HEADERS,
            (watched_row(entry) for entry in exportable),
            max_bytes=self.max_bytes,
        )
        result.rows = len(exportable)
        logger.info(
            "Exported %d watched entries to %d file(s) in %s",
            result.rows,
            len(result.files),
            self.pending_dir,
        )
        return result

    def export_watchlist(
        self,
        entries: Sequence[WatchlistEntry],
        moment: Optional[datetime] = None,
    ) -> ExportResult:
        """Export the watchlist as its own file, for the watchlist importer."""
        result = ExportResult(kind="watchlist")
        exportable = [entry for entry in entries if entry.movie.title.strip()]
        if not exportable:
            logger.info("Nothing to export for the watchlist")
            return result

        result.files = csv_format.write_chunked(
            self.pending_dir,
            f"letterboxd_watchlist_{_timestamp(moment)}",
            WATCHLIST_HEADERS,
            (watchlist_row(entry) for entry in exportable),
            max_bytes=self.max_bytes,
        )
        result.rows = len(exportable)
        logger.info(
            "Exported %d watchlist films to %d file(s) in %s",
            result.rows,
            len(result.files),
            self.pending_dir,
        )
        return result


def _parse_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def read_confirmations(path: Path) -> list[tuple[str, str, str]]:
    """Read back an exported CSV as (film key, watched date, fingerprint).

    Parsing the file that was actually uploaded, rather than trusting a
    side-channel, keeps ``confirm`` honest: whatever Letterboxd received is
    what gets marked as imported.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    rows = csv_format.parse_dicts(text)

    records: list[tuple[str, str, str]] = []
    for row in rows:
        movie = Movie(
            title=(row.get("Title") or "").strip(),
            year=_parse_int(row.get("Year", "")),
            tmdb_id=_parse_int(row.get("tmdbID", "")),
            imdb_id=(row.get("imdbID") or "").strip() or None,
        )
        watched_date = (row.get("WatchedDate") or "").strip()
        fingerprint = fingerprint_of(
            rating10=_parse_int(row.get("Rating10", "")),
            rewatch=(row.get("Rewatch") or "").strip().lower() == "true",
            tags=row.get("Tags", ""),
            review=row.get("Review", ""),
        )
        records.append((movie.key, watched_date, fingerprint))

    return records


def is_watchlist_file(path: Path) -> bool:
    """True when the CSV is a watchlist export (no diary state to confirm)."""
    with open(path, "r", encoding="utf-8") as handle:
        header = handle.readline().strip()
    return header == csv_format.format_row(WATCHLIST_HEADERS)


def archive_file(path: Path, done_dir: Path, moment: Optional[datetime] = None) -> Path:
    """Move a confirmed CSV into the timestamped archive directory."""
    target_dir = Path(done_dir) / (moment or datetime.now()).strftime("%Y%m%d-%H%M%S")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / Path(path).name
    Path(path).replace(target)
    return target
