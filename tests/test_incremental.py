"""Incremental export: new, changed, unchanged, confirmed."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.exporters.letterboxd import (
    LetterboxdExporter,
    WATCHLIST_HEADERS,
    archive_file,
    is_watchlist_file,
    read_confirmations,
    select_pending,
)
from src.models import Movie, WatchEntry, WatchlistEntry
from src.web.database import Database


def entry(tmdb_id=11, watched="2023-06-18", rating10=8, review=None, tags=None, rewatch=False):
    return WatchEntry(
        movie=Movie(title="Star Wars", year=1977, tmdb_id=tmdb_id, imdb_id="tt0076759"),
        watched_date=date.fromisoformat(watched) if watched else None,
        rating10=rating10,
        review=review,
        tags=tags or [],
        rewatch=rewatch,
    )


class TestFingerprint:
    def test_same_user_data_gives_the_same_fingerprint(self):
        assert entry().fingerprint == entry().fingerprint

    def test_rating_change_changes_the_fingerprint(self):
        assert entry(rating10=8).fingerprint != entry(rating10=9).fingerprint

    def test_review_change_changes_the_fingerprint(self):
        assert entry(review="Good").fingerprint != entry(review="Great").fingerprint

    def test_tag_change_changes_the_fingerprint(self):
        assert entry(tags=["scifi"]).fingerprint != entry(tags=["scifi", "rewatch"]).fingerprint

    def test_rewatch_change_changes_the_fingerprint(self):
        assert entry(rewatch=False).fingerprint != entry(rewatch=True).fingerprint

    def test_metadata_only_change_does_not(self):
        # Enriching directors later must not resurface hundreds of entries.
        first = entry()
        second = entry()
        second.movie.directors = ["George Lucas"]
        assert first.fingerprint == second.fingerprint

    def test_state_key_is_film_plus_date(self):
        assert entry().state_key == ("tmdb:11", "2023-06-18")
        assert entry(watched=None).state_key == ("tmdb:11", "")


class TestSelectPending:
    def test_unknown_entry_is_pending(self):
        pending, unchanged = select_pending([entry()], {})
        assert len(pending) == 1 and unchanged == 0

    def test_confirmed_and_untouched_entry_is_skipped(self):
        item = entry()
        pending, unchanged = select_pending([item], {item.state_key: item.fingerprint})
        assert pending == [] and unchanged == 1

    def test_changed_rating_makes_it_pending_again(self):
        confirmed = entry(rating10=8)
        state = {confirmed.state_key: confirmed.fingerprint}
        pending, unchanged = select_pending([entry(rating10=9)], state)
        assert len(pending) == 1 and unchanged == 0

    def test_added_review_makes_it_pending_again(self):
        confirmed = entry(review=None)
        state = {confirmed.state_key: confirmed.fingerprint}
        pending, _ = select_pending([entry(review="A classic.")], state)
        assert len(pending) == 1

    def test_a_new_date_for_the_same_film_is_a_new_entry(self):
        confirmed = entry(watched="2023-06-18")
        state = {confirmed.state_key: confirmed.fingerprint}
        pending, unchanged = select_pending([confirmed, entry(watched="2026-01-02")], state)
        assert len(pending) == 1 and unchanged == 1
        assert pending[0].watched_date == date(2026, 1, 2)


class TestExportModes:
    def test_incremental_writes_only_pending_entries(self, tmp_path):
        confirmed = entry(tmdb_id=11)
        fresh = entry(tmdb_id=22)
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watched(
            [confirmed, fresh], state={confirmed.state_key: confirmed.fingerprint}
        )
        assert result.rows == 1
        assert result.skipped_unchanged == 1

    def test_full_ignores_the_state(self, tmp_path):
        confirmed = entry()
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watched([confirmed], state=None)
        assert result.rows == 1

    def test_nothing_pending_writes_no_file(self, tmp_path):
        confirmed = entry()
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watched(
            [confirmed], state={confirmed.state_key: confirmed.fingerprint}
        )
        assert result.files == [] and result.rows == 0

    def test_watchlist_is_its_own_file(self, tmp_path):
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watchlist(
            [WatchlistEntry(movie=Movie(title="Taxi Driver", year=1976, tmdb_id=103))]
        )
        assert len(result.files) == 1
        content = result.files[0].read_text(encoding="utf-8")
        assert content.startswith("Title,Year,tmdbID,imdbID\n")
        assert is_watchlist_file(result.files[0])


class TestConfirmRoundTrip:
    def test_confirmations_match_the_exported_entries(self, tmp_path):
        entries = [
            entry(tmdb_id=11, review='He said "no". Then, silence.\nEnd.'),
            entry(tmdb_id=22, rating10=None, tags=["scifi", "rewatch"]),
        ]
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watched(entries, state=None)

        records = read_confirmations(result.files[0])
        state = {(key, watched): fingerprint for key, watched, fingerprint in records}

        pending, unchanged = select_pending(entries, state)
        assert pending == [] and unchanged == len(entries)

    def test_entry_without_a_date_round_trips(self, tmp_path):
        item = entry(watched=None)
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watched([item], state=None)
        records = read_confirmations(result.files[0])
        assert records[0][1] == ""
        state = {(key, watched): fingerprint for key, watched, fingerprint in records}
        assert select_pending([item], state) == ([], 1)

    def test_title_matched_film_round_trips(self, tmp_path):
        item = WatchEntry(
            movie=Movie(title="Obscure Film", year=1999),
            watched_date=date(2024, 3, 1),
            rating10=6,
        )
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watched([item], state=None)
        records = read_confirmations(result.files[0])
        assert records[0][0] == "title:obscure film|1999"
        state = {(key, watched): fingerprint for key, watched, fingerprint in records}
        assert select_pending([item], state) == ([], 1)


class TestDatabaseState:
    @pytest.fixture()
    def database(self, tmp_path):
        with Database(tmp_path / "movies.db") as database:
            yield database

    def test_state_starts_empty(self, database):
        assert database.get_export_state() == {}

    def test_confirm_then_reexport_is_a_no_op(self, database, tmp_path):
        item = entry()
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watched([item], state=database.get_export_state())
        assert result.rows == 1

        database.mark_confirmed(read_confirmations(result.files[0]), source_file="x.csv")

        again = exporter.export_watched([item], state=database.get_export_state())
        assert again.rows == 0 and again.skipped_unchanged == 1

    def test_confirm_is_idempotent(self, database, tmp_path):
        item = entry()
        exporter = LetterboxdExporter(tmp_path)
        result = exporter.export_watched([item], state=None)
        records = read_confirmations(result.files[0])

        inserted, updated = database.mark_confirmed(records)
        assert (inserted, updated) == (1, 0)
        inserted, updated = database.mark_confirmed(records)
        assert (inserted, updated) == (0, 1)
        assert database.count_export_state() == 1

    def test_editing_a_review_after_confirmation_makes_it_pending(self, database, tmp_path):
        item = entry(review=None)
        exporter = LetterboxdExporter(tmp_path)
        first = exporter.export_watched([item], state=database.get_export_state())
        database.mark_confirmed(read_confirmations(first.files[0]))

        edited = entry(review="Second viewing, still perfect.")
        second = exporter.export_watched([edited], state=database.get_export_state())
        assert second.rows == 1

    def test_confirm_updates_the_last_confirm_timestamp(self, database, tmp_path):
        assert database.get_sync_status().last_confirm is None
        database.mark_confirmed([("tmdb:11", "2023-06-18", "abc")])
        assert database.get_sync_status().last_confirm is not None


class TestArchiving:
    def test_confirmed_file_moves_to_a_timestamped_folder(self, tmp_path):
        pending = tmp_path / "pending"
        pending.mkdir()
        source = pending / "letterboxd_watched.csv"
        source.write_text("Title\nTop Gun\n", encoding="utf-8")

        target = archive_file(source, tmp_path / "done", datetime(2026, 9, 4, 9, 0, 0))
        assert not source.exists()
        assert target.parent.name == "20260904-090000"
        assert target.read_text(encoding="utf-8") == "Title\nTop Gun\n"

    def test_watchlist_file_is_recognised(self, tmp_path):
        path = tmp_path / "wl.csv"
        path.write_text(",".join(WATCHLIST_HEADERS) + "\n", encoding="utf-8")
        assert is_watchlist_file(path)
