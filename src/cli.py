"""Command line interface.

    python -m src.cli sync                 pull the source into the database
    python -m src.cli export               write the entries not yet imported
    python -m src.cli export --full        write every entry
    python -m src.cli confirm <file.csv>   mark a file as imported
    python -m src.cli status               counters
    python -m src.cli serve                web dashboard
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

if __package__ in (None, ""):  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config
from src.exporters.letterboxd import (
    ExportResult,
    LetterboxdExporter,
    archive_file,
    is_watchlist_file,
    read_confirmations,
    select_pending,
)
from src.logging_setup import setup_logging
from src.sync import build_source, sync_to_database
from src.web.database import Database, utcnow

logger = logging.getLogger("letterboxd-sync")


def _prepare(log_name: str) -> Database:
    Config.ensure_directories()
    setup_logging(
        Config.LOG_DIR,
        level=Config.LOG_LEVEL,
        console_level=Config.CONSOLE_LOG_LEVEL,
        filename=log_name,
    )
    return Database(Config.DB_PATH)


def _fail_on_config() -> int:
    errors = Config.validate()
    if not errors:
        return 0
    print("Configuration errors:")
    for error in errors:
        print(f"  - {error}")
    print("\nCheck your .env file (see .env.example).")
    return 1


def _describe(result: ExportResult) -> None:
    if not result.files:
        return
    for path in result.files:
        print(f"    {path}  ({path.stat().st_size:,} bytes)")


# --------------------------------------------------------------------- sync


def command_sync(args: argparse.Namespace) -> int:
    if _fail_on_config():
        return 1
    database = _prepare("sync.log")

    source = build_source(args.source)
    result = sync_to_database(
        database, source, include_watchlist=not args.no_watchlist
    )
    if result["status"] != "success":
        print(f"Sync failed: {result.get('error')}")
        return 1

    print(
        f"Synced from {result['source']}: "
        f"{result['watched']} watched, {result['watchlist']} watchlist"
    )
    return 0


# ------------------------------------------------------------------- export


def command_export(args: argparse.Namespace) -> int:
    database = _prepare("export.log")

    pending_dir = Path(args.out_dir) if args.out_dir else Config.pending_dir()
    exporter = LetterboxdExporter(pending_dir, max_bytes=Config.MAX_CSV_BYTES)
    moment = datetime.now()

    entries = database.get_watch_entries()
    state = None if args.full else database.get_export_state()
    watched = exporter.export_watched(entries, state=state, moment=moment)

    mode = "full" if args.full else "incremental"
    print(f"Export ({mode}) from {len(entries)} watched entries in the database")
    print(f"  watched   : {watched.rows} row(s), {len(watched.files)} file(s)")
    if watched.skipped_unchanged:
        print(f"              {watched.skipped_unchanged} unchanged since last confirmation")
    _describe(watched)

    watchlist = None
    include_watchlist = Config.EXPORT_WATCHLIST and not args.no_watchlist
    if include_watchlist:
        watchlist = exporter.export_watchlist(database.get_watchlist_entries(), moment=moment)
        print(f"  watchlist : {watchlist.rows} row(s), {len(watchlist.files)} file(s)")
        _describe(watchlist)

    total_files = len(watched.files) + (len(watchlist.files) if watchlist else 0)
    if total_files:
        database.update_sync_status(last_export=utcnow())
        print("\nUpload the file(s) at https://letterboxd.com/import, then run:")
        for path in watched.files:
            print(f"  python -m src.cli confirm \"{path}\"")
    else:
        print("\nNothing to export: everything already confirmed as imported.")

    return 0


# ------------------------------------------------------------------ confirm


def command_confirm(args: argparse.Namespace) -> int:
    database = _prepare("export.log")

    paths = [Path(item) for item in args.files]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        for path in missing:
            print(f"File not found: {path}")
        return 1

    moment = datetime.now()
    total_inserted = 0
    total_updated = 0

    for path in paths:
        if is_watchlist_file(path):
            print(f"{path.name}: watchlist file, no diary state to record")
            if not args.keep:
                archived = archive_file(path, Config.done_dir(), moment)
                print(f"  archived to {archived}")
            continue

        records = read_confirmations(path)
        inserted, updated = database.mark_confirmed(records, source_file=path.name)
        total_inserted += inserted
        total_updated += updated
        print(f"{path.name}: {len(records)} row(s) confirmed ({inserted} new, {updated} updated)")

        if not args.keep:
            archived = archive_file(path, Config.done_dir(), moment)
            print(f"  archived to {archived}")

    logger.info(
        "Confirmed %d file(s): %d new entries, %d updated",
        len(paths),
        total_inserted,
        total_updated,
    )
    return 0


# ------------------------------------------------------------------- status


def command_status(args: argparse.Namespace) -> int:
    database = _prepare("status.log")

    entries = database.get_watch_entries()
    watchlist = database.get_watchlist_entries()
    state = database.get_export_state()
    pending, unchanged = select_pending(entries, state)

    sync_status = database.get_sync_status()
    pending_files = sorted(Config.pending_dir().glob("*.csv"))

    print("Letterboxd Sync status")
    print(f"  source             : {Config.PRIMARY_SOURCE}")
    print(f"  TMDB enrichment    : {'on' if Config.tmdb_enabled() else 'off'}")
    print(f"  watched entries    : {len(entries)}")
    print(f"  watchlist films    : {len(watchlist)}")
    print(f"  confirmed imported : {unchanged}")
    print(f"  pending export     : {len(pending)}")
    print(f"  last sync (UTC)    : {sync_status.last_sync or 'never'}")
    print(f"  last export (UTC)  : {sync_status.last_export or 'never'}")
    print(f"  last confirm (UTC) : {sync_status.last_confirm or 'never'}")
    print(f"  CSV files pending  : {len(pending_files)}")
    for path in pending_files:
        print(f"    {path.name}  ({path.stat().st_size:,} bytes)")

    if sync_status.status == "error" and sync_status.error_message:
        print(f"  last error         : {sync_status.error_message}")

    return 0


# -------------------------------------------------------------------- serve


def command_serve(args: argparse.Namespace) -> int:
    if _fail_on_config():
        return 1
    _prepare("serve.log")

    import uvicorn

    port = args.port or Config.WEB_PORT
    print(f"Dashboard on http://localhost:{port}")
    uvicorn.run("src.web.app:app", host=args.host, port=port, reload=False, log_level="info")
    return 0


# ---------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="letterboxd-sync",
        description="Export a watch history to Letterboxd import CSV files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="pull the source into the database")
    sync_parser.add_argument("--source", choices=["simkl", "plex", "tautulli"], default=None)
    sync_parser.add_argument("--no-watchlist", action="store_true", help="skip the watchlist")
    sync_parser.set_defaults(func=command_sync)

    export_parser = subparsers.add_parser("export", help="write import-ready CSV files")
    mode = export_parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--incremental",
        action="store_true",
        help="only new or changed entries (default)",
    )
    mode.add_argument("--full", action="store_true", help="every entry, ignoring export state")
    export_parser.add_argument("--no-watchlist", action="store_true", help="skip the watchlist file")
    export_parser.add_argument("--out-dir", default=None, help="override the output directory")
    export_parser.set_defaults(func=command_export)

    confirm_parser = subparsers.add_parser(
        "confirm", help="mark the rows of a CSV as imported on Letterboxd"
    )
    confirm_parser.add_argument("files", nargs="+", help="CSV file(s) that were imported")
    confirm_parser.add_argument(
        "--keep", action="store_true", help="do not move the file to output/done"
    )
    confirm_parser.set_defaults(func=command_confirm)

    status_parser = subparsers.add_parser("status", help="show counters")
    status_parser.set_defaults(func=command_status)

    serve_parser = subparsers.add_parser("serve", help="run the web dashboard")
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.set_defaults(func=command_serve)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:  # pragma: no cover
        print("Interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
