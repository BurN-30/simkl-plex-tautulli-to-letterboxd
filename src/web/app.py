"""FastAPI web application."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.config import Config
from src.models import rating10_to_rating5
from src.web.database import Database, utcnow
from src.web.sync_service import SyncService

logger = logging.getLogger(__name__)

# Initialize database
db = Database(Config.DB_PATH)
sync_service: Optional[SyncService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global sync_service

    # Startup
    logger.info("Starting web application...")
    sync_service = SyncService(db)

    # Optional background sync; the weekly scheduled task is the normal path.
    sync_service.start(interval_minutes=int(os.getenv("SYNC_INTERVAL", "0") or 0))

    yield

    # Shutdown
    if sync_service:
        sync_service.stop()


app = FastAPI(
    title="Letterboxd Sync",
    description="Manage your movie watch history",
    lifespan=lifespan,
)

# Mount static files
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


# Pydantic models for API
class MovieUpdate(BaseModel):
    """Fields the dashboard can edit.

    ``rating10`` is authoritative (it is what the CSV exports); ``rating`` on
    the 0.5-5 scale is recomputed from it so the statistics stay consistent.
    """

    rating10: Optional[int] = None
    watched_date: Optional[str] = None
    rewatch: Optional[bool] = None
    tags: Optional[str] = None
    review: Optional[str] = None


class SyncResponse(BaseModel):
    status: str
    message: str
    watched_count: Optional[int] = None
    watchlist_count: Optional[int] = None


# ============== HTML Pages ==============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page."""
    stats = db.get_statistics()
    sync_status = db.get_sync_status()
    years = db.get_years()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": stats,
            "sync_status": sync_status,
            "years": years,
        },
    )


@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request):
    """Watchlist page."""
    return templates.TemplateResponse(
        "watchlist.html",
        {"request": request},
    )


@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    """Statistics page."""
    stats = db.get_statistics()
    return templates.TemplateResponse(
        "stats.html",
        {"request": request, "stats": stats},
    )


# ============== API Endpoints ==============

@app.get("/api/movies")
async def get_movies(
    watched: Optional[bool] = Query(True),
    watchlist: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    min_rating: Optional[float] = Query(None),
    max_rating: Optional[float] = Query(None),
    sort_by: str = Query("watched_date"),
    sort_order: str = Query("desc"),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """Get movies with filters."""
    movies = db.get_all_movies(
        watched=watched,
        watchlist=watchlist,
        search=search,
        year=year,
        min_rating=min_rating,
        max_rating=max_rating,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

    total = db.count_movies(watched=watched, watchlist=watchlist, search=search)

    return {
        "movies": [m.to_dict() for m in movies],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/movies/{movie_id}")
async def get_movie(movie_id: int):
    """Get a single movie."""
    movie = db.get_movie_by_id(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie.to_dict()


@app.patch("/api/movies/{movie_id}")
async def update_movie(movie_id: int, updates: MovieUpdate):
    """Update a movie."""
    update_data = updates.model_dump(exclude_unset=True)

    # Parse date if provided
    if "watched_date" in update_data and update_data["watched_date"]:
        try:
            update_data["watched_date"] = date.fromisoformat(update_data["watched_date"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

    if "rating10" in update_data:
        rating10 = update_data["rating10"]
        if rating10 is not None and not 1 <= rating10 <= 10:
            raise HTTPException(status_code=400, detail="rating10 must be between 1 and 10")
        update_data["rating"] = rating10_to_rating5(rating10)

    movie = db.update_movie(movie_id, update_data)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    return movie.to_dict()


@app.delete("/api/movies/{movie_id}")
async def delete_movie(movie_id: int):
    """Delete a movie."""
    if db.delete_movie(movie_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Movie not found")


@app.get("/api/stats")
async def get_stats():
    """Get statistics."""
    return db.get_statistics()


@app.get("/api/years")
async def get_years():
    """Get list of years."""
    return db.get_years()


@app.get("/api/sync/status")
async def get_sync_status():
    """Get sync status."""
    status = db.get_sync_status()
    return {
        "last_sync": status.last_sync.isoformat() if status.last_sync else None,
        "movies_count": status.movies_count,
        "watchlist_count": status.watchlist_count,
        "status": status.status,
        "error_message": status.error_message,
        "is_syncing": sync_service.is_syncing if sync_service else False,
    }


@app.post("/api/sync/trigger")
async def trigger_sync():
    """Manually trigger a sync."""
    if not sync_service:
        raise HTTPException(status_code=503, detail="Sync service not available")

    if sync_service.is_syncing:
        return {"status": "already_syncing", "message": "Sync already in progress"}

    # Run sync in background thread (non-blocking)
    import threading
    thread = threading.Thread(target=sync_service.sync)
    thread.start()

    return {"status": "started", "message": "Sync started"}


# ============== Auth Endpoints ==============

_oauth_instance = None
_oauth_state = {"status": "idle", "error": None}


@app.get("/api/auth/status")
async def auth_status():
    """Check authentication status and OAuth state."""
    if Config.PRIMARY_SOURCE != "simkl":
        return {"authenticated": True}
    authenticated = Config.SIMKL_TOKEN_FILE.exists()
    return {
        "authenticated": authenticated,
        "oauth": _oauth_state if not authenticated else None,
    }


@app.post("/api/auth/start")
async def auth_start():
    """Start Simkl OAuth flow. Returns auth URL to open in browser."""
    global _oauth_instance, _oauth_state
    import threading
    from src.auth.simkl_oauth import SimklOAuth

    if Config.SIMKL_TOKEN_FILE.exists():
        return {"status": "already_authenticated"}

    if not Config.SIMKL_CLIENT_ID:
        _oauth_state = {"status": "error", "error": "SIMKL_CLIENT_ID not configured in .env"}
        return {"status": "error", "error": _oauth_state["error"]}

    # Already pending — return existing auth URL
    if _oauth_state["status"] == "pending" and _oauth_instance:
        return {"status": "pending", "auth_url": _oauth_instance.get_auth_url()}

    _oauth_instance = SimklOAuth(Config.SIMKL_CLIENT_ID, Config.SIMKL_CLIENT_SECRET, Config.SIMKL_TOKEN_FILE, port=Config.OAUTH_PORT)
    try:
        _oauth_instance.start_callback_server()
    except OSError as e:
        _oauth_instance = None
        _oauth_state = {"status": "error", "error": f"Port {Config.OAUTH_PORT} in use — change OAUTH_PORT in .env ({e})"}
        return {"status": "error", "error": _oauth_state["error"]}

    _oauth_state = {"status": "pending", "error": None}
    logger.info("OAuth callback server started, waiting for Simkl redirect...")

    def wait_and_exchange():
        global _oauth_state
        token = _oauth_instance.wait_for_callback(timeout=300)
        if token:
            _oauth_state = {"status": "success", "error": None}
            logger.info("Simkl OAuth authentication successful")
        else:
            error = getattr(_oauth_instance, '_last_error', None) or "Unknown authentication error"
            _oauth_state = {"status": "error", "error": error}
            logger.error(f"Simkl OAuth failed: {error}")

    threading.Thread(target=wait_and_exchange, daemon=True).start()

    return {"status": "pending", "auth_url": _oauth_instance.get_auth_url()}


# ============== Export ==============


@app.post("/api/export")
async def run_export(full: bool = Query(False), watchlist: bool = Query(True)):
    """Write import-ready CSV files into output/pending.

    The dashboard never talks to Letterboxd: it only produces files that the
    member uploads themselves at letterboxd.com/import.
    """
    from src.exporters.letterboxd import LetterboxdExporter

    exporter = LetterboxdExporter(Config.pending_dir(), max_bytes=Config.MAX_CSV_BYTES)
    state = None if full else db.get_export_state()
    watched_result = exporter.export_watched(db.get_watch_entries(), state=state)

    payload = {
        "mode": "full" if full else "incremental",
        "watched_rows": watched_result.rows,
        "watched_files": [path.name for path in watched_result.files],
        "unchanged": watched_result.skipped_unchanged,
    }

    if watchlist:
        watchlist_result = exporter.export_watchlist(db.get_watchlist_entries())
        payload["watchlist_rows"] = watchlist_result.rows
        payload["watchlist_files"] = [path.name for path in watchlist_result.files]

    if watched_result.files or payload.get("watchlist_files"):
        db.update_sync_status(last_export=utcnow())

    return payload


@app.get("/api/export/pending")
async def list_pending():
    """List the CSV files waiting to be imported."""
    files = sorted(Config.pending_dir().glob("*.csv"))
    return {
        "files": [
            {"name": path.name, "bytes": path.stat().st_size}
            for path in files
        ]
    }


@app.get("/api/export/csv")
async def export_csv(watchlist: bool = Query(False)):
    """Download a single CSV in the Letterboxd import format."""
    from fastapi.responses import Response

    from src.exporters.letterboxd import (
        WATCHED_HEADERS,
        WATCHLIST_HEADERS,
        watched_row,
        watchlist_row,
    )
    from src.letterboxd import csv_format

    if watchlist:
        content = csv_format.render(
            WATCHLIST_HEADERS, [watchlist_row(entry) for entry in db.get_watchlist_entries()]
        )
        filename = "letterboxd_watchlist.csv"
    else:
        content = csv_format.render(
            WATCHED_HEADERS, [watched_row(entry) for entry in db.get_watch_entries()]
        )
        filename = "letterboxd_watched.csv"

    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
