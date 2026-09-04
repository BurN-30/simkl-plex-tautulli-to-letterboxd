"""Mapping of Simkl payloads onto exportable entries."""

from __future__ import annotations

from datetime import date

from src.exporters.letterboxd import WATCHED_HEADERS, watched_row
from src.models import rating10_to_rating5
from src.sources.simkl import _as_items, merge_ratings, parse_movie, parse_watch_entry


def simkl_item(**overrides):
    """A realistic ``/sync/all-items/movies/completed`` item."""
    item = {
        "added_to_watchlist_at": "2025-01-21T05:13:38Z",
        "last_watched_at": "2023-06-18T00:00:00Z",
        "user_rated_at": "2025-05-15T08:18:19Z",
        "user_rating": 10,
        "status": "completed",
        "movie": {
            "title": "Star Wars",
            "year": 1977,
            "ids": {
                "simkl": 53078,
                "slug": "star-wars",
                "imdb": "tt0076759",
                "tmdb": "11",
                "letterboxd": "star-wars",
            },
        },
    }
    item.update(overrides)
    return item


class TestResponseShape:
    def test_accepts_the_wrapped_shape(self):
        assert len(_as_items({"movies": [simkl_item()]})) == 1

    def test_accepts_a_bare_list(self):
        assert len(_as_items([simkl_item()])) == 1

    def test_empty_account_returns_nothing(self):
        assert _as_items(None) == []
        assert _as_items({}) == []


class TestMovieMapping:
    def test_ids_are_typed(self):
        movie = parse_movie(simkl_item()["movie"])
        # Simkl serialises tmdb as a string; the CSV needs a bare number.
        assert movie.tmdb_id == 11
        assert movie.imdb_id == "tt0076759"
        assert movie.simkl_id == 53078
        assert movie.letterboxd_slug == "star-wars"
        assert movie.year == 1977

    def test_missing_ids_become_none(self):
        movie = parse_movie({"title": "Obscure", "year": 1999, "ids": {"simkl": 1}})
        assert movie.tmdb_id is None
        assert movie.imdb_id is None
        assert not movie.has_exact_id

    def test_key_prefers_tmdb_then_imdb_then_title(self):
        assert parse_movie(simkl_item()["movie"]).key == "tmdb:11"
        assert parse_movie({"title": "X", "ids": {"imdb": "tt1"}}).key == "imdb:tt1"
        assert parse_movie({"title": "X", "year": 1999, "ids": {}}).key == "title:x|1999"


class TestWatchDate:
    def test_midnight_marker_keeps_its_day(self):
        entry = parse_watch_entry(simkl_item())
        assert entry.watched_date == date(2023, 6, 18)

    def test_real_timestamp_is_truncated_without_conversion_by_default(self):
        entry = parse_watch_entry(simkl_item(last_watched_at="2025-10-31T23:39:04Z"))
        assert entry.watched_date == date(2025, 10, 31)

    def test_conversion_is_applied_when_a_zone_is_given(self):
        entry = parse_watch_entry(
            simkl_item(last_watched_at="2025-10-31T23:39:04Z"), "Europe/Paris"
        )
        assert entry.watched_date == date(2025, 11, 1)

    def test_midnight_marker_is_unaffected_by_conversion(self):
        # Paris is ahead of UTC, so 00:00Z stays on the same calendar day.
        entry = parse_watch_entry(simkl_item(), "Europe/Paris")
        assert entry.watched_date == date(2023, 6, 18)

    def test_missing_date_is_none(self):
        assert parse_watch_entry(simkl_item(last_watched_at=None)).watched_date is None


class TestRating:
    def test_rating10_is_kept_as_an_integer(self):
        assert parse_watch_entry(simkl_item()).rating10 == 10

    def test_unrated_entry_has_no_rating(self):
        assert parse_watch_entry(simkl_item(user_rating=None)).rating10 is None

    def test_out_of_range_rating_is_dropped(self):
        assert parse_watch_entry(simkl_item(user_rating=42)).rating10 is None

    def test_conversion_to_the_five_star_scale_is_display_only(self):
        assert rating10_to_rating5(10) == 5.0
        assert rating10_to_rating5(7) == 3.5
        assert rating10_to_rating5(1) == 0.5
        assert rating10_to_rating5(None) is None

    def test_ratings_list_overrides_the_completed_payload(self):
        entries = [parse_watch_entry(simkl_item(user_rating=None))]
        updated = merge_ratings(entries, [simkl_item(user_rating=8)])
        assert updated == 1
        assert entries[0].rating10 == 8

    def test_ratings_for_unknown_films_are_ignored(self):
        entries = [parse_watch_entry(simkl_item())]
        other = simkl_item(user_rating=3)
        other["movie"]["ids"]["simkl"] = 999999
        assert merge_ratings(entries, [other]) == 0
        assert entries[0].rating10 == 10


class TestCsvRow:
    def test_row_layout_matches_the_headers(self):
        row = watched_row(parse_watch_entry(simkl_item()))
        assert len(row) == len(WATCHED_HEADERS)
        assert dict(zip(WATCHED_HEADERS, row)) == {
            "tmdbID": "11",
            "imdbID": "tt0076759",
            "Title": "Star Wars",
            "Year": "1977",
            "Directors": "",
            "WatchedDate": "2023-06-18",
            "Rating10": "10",
            "Rewatch": "false",
            "Tags": "",
            "Review": "",
        }

    def test_rating_column_is_never_emitted_alongside_rating10(self):
        # Letterboxd keeps whichever rating column comes second, so only one
        # of them may ever be present.
        assert "Rating" not in WATCHED_HEADERS
        assert "Rating10" in WATCHED_HEADERS

    def test_unknown_directors_leave_an_empty_column(self):
        row = dict(zip(WATCHED_HEADERS, watched_row(parse_watch_entry(simkl_item()))))
        assert row["Directors"] == ""

    def test_unrated_film_leaves_the_rating_column_empty(self):
        entry = parse_watch_entry(simkl_item(user_rating=None))
        assert dict(zip(WATCHED_HEADERS, watched_row(entry)))["Rating10"] == ""
