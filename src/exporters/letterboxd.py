"""Letterboxd CSV exporter."""

import csv
import logging
from datetime import date
from pathlib import Path
from typing import List

from src.models import Movie, WatchEntry, WatchlistEntry

logger = logging.getLogger(__name__)


class LetterboxdExporter:
    """Export movies to Letterboxd-compatible CSV format."""

    WATCHED_HEADERS = [
        "imdbID",
        "tmdbID",
        "Title",
        "Year",
        "Directors",
        "WatchedDate",
        "Rating",
        "Rewatch",
        "Tags",
        "Review",
    ]

    WATCHLIST_HEADERS = [
        "imdbID",
        "tmdbID",
        "Title",
        "Year",
        "Directors",
    ]

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_watched(
        self, entries: List[WatchEntry], filename: str = "letterboxd_watched.csv"
    ) -> Path:
        """
        Export watched movies to CSV.

        Args:
            entries: List of WatchEntry objects
            filename: Output filename

        Returns:
            Path to the created CSV file
        """
        output_path = self.output_dir / filename
        valid_entries = []
        not_found = []

        for entry in entries:
            if entry.movie.tmdb_id or entry.movie.imdb_id:
                valid_entries.append(entry)
            else:
                not_found.append(entry)

        # Write main CSV
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.WATCHED_HEADERS)

            for entry in valid_entries:
                row = self._format_watched_row(entry)
                writer.writerow(row)

        logger.info(f"Exported {len(valid_entries)} watched movies to {output_path}")

        # Write not found movies
        if not_found:
            self._export_not_found(not_found, "not_found_watched.csv")

        return output_path

    def export_watchlist(
        self, entries: List[WatchlistEntry], filename: str = "letterboxd_watchlist.csv"
    ) -> Path:
        """
        Export watchlist to CSV.

        Args:
            entries: List of WatchlistEntry objects
            filename: Output filename

        Returns:
            Path to the created CSV file
        """
        output_path = self.output_dir / filename
        valid_entries = []
        not_found = []

        for entry in entries:
            if entry.movie.tmdb_id or entry.movie.imdb_id:
                valid_entries.append(entry)
            else:
                not_found.append(entry)

        # Write main CSV
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.WATCHLIST_HEADERS)

            for entry in valid_entries:
                row = self._format_watchlist_row(entry)
                writer.writerow(row)

        logger.info(f"Exported {len(valid_entries)} watchlist movies to {output_path}")

        # Write not found movies
        if not_found:
            self._export_not_found_watchlist(not_found, "not_found_watchlist.csv")

        return output_path

    def _format_watched_row(self, entry: WatchEntry) -> list:
        """Format a WatchEntry as a CSV row."""
        movie = entry.movie

        # Format rating (0.5-5 scale, or empty)
        rating_str = ""
        if entry.rating is not None:
            rating_str = str(entry.rating)

        # Format date
        date_str = ""
        if entry.watched_date:
            date_str = entry.watched_date.isoformat()

        # Format directors
        directors_str = ", ".join(movie.directors) if movie.directors else ""

        # Format rewatch
        rewatch_str = "true" if entry.rewatch else "false"

        # Format tags
        tags_str = ", ".join(entry.tags) if entry.tags else ""

        return [
            movie.imdb_id or "",
            str(movie.tmdb_id) if movie.tmdb_id else "",
            movie.title,
            str(movie.year) if movie.year else "",
            directors_str,
            date_str,
            rating_str,
            rewatch_str,
            tags_str,
            entry.review or "",
        ]

    def _format_watchlist_row(self, entry: WatchlistEntry) -> list:
        """Format a WatchlistEntry as a CSV row."""
        movie = entry.movie

        # Format directors
        directors_str = ", ".join(movie.directors) if movie.directors else ""

        return [
            movie.imdb_id or "",
            str(movie.tmdb_id) if movie.tmdb_id else "",
            movie.title,
            str(movie.year) if movie.year else "",
            directors_str,
        ]

    def _export_not_found(
        self, entries: List[WatchEntry], filename: str
    ) -> None:
        """Export entries that couldn't be matched to a separate CSV."""
        output_path = self.output_dir / filename

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Title", "Year", "WatchedDate", "Rating", "Reason"])

            for entry in entries:
                writer.writerow([
                    entry.movie.title,
                    entry.movie.year or "",
                    entry.watched_date.isoformat() if entry.watched_date else "",
                    entry.rating or "",
                    "No TMDB/IMDB ID found",
                ])

        logger.warning(
            f"{len(entries)} watched movies could not be matched. "
            f"See {output_path}"
        )

    def _export_not_found_watchlist(
        self, entries: List[WatchlistEntry], filename: str
    ) -> None:
        """Export watchlist entries that couldn't be matched."""
        output_path = self.output_dir / filename

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Title", "Year", "AddedDate", "Reason"])

            for entry in entries:
                writer.writerow([
                    entry.movie.title,
                    entry.movie.year or "",
                    entry.added_date.isoformat() if entry.added_date else "",
                    "No TMDB/IMDB ID found",
                ])

        logger.warning(
            f"{len(entries)} watchlist movies could not be matched. "
            f"See {output_path}"
        )
