"""FastAPI web application."""

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.config import Config
from src.web.database import Database
from src.web.sync_service import SyncService

logger = logging.getLogger(__name__)

# Initialize database
db = Database()
sync_service: Optional[SyncService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global sync_service

    # Startup
    logger.info("Starting web application...")
    sync_service = SyncService(db)

    # Start background sync (every 15 minutes)
    sync_interval = int(Config.SYNC_INTERVAL) if hasattr(Config, 'SYNC_INTERVAL') else 15
    sync_service.start(interval_minutes=sync_interval)

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
    rating: Optional[float] = None
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
_oauth_pending = False


@app.get("/api/auth/status")
async def auth_status():
    """Check authentication status for the configured source."""
    if Config.PRIMARY_SOURCE != "simkl":
        return {"authenticated": True}
    return {"authenticated": Config.SIMKL_TOKEN_FILE.exists()}


@app.post("/api/auth/start")
async def auth_start():
    """Start Simkl OAuth flow. Returns auth URL to open in browser."""
    global _oauth_instance, _oauth_pending
    import threading
    from src.auth.simkl_oauth import SimklOAuth

    if Config.SIMKL_TOKEN_FILE.exists():
        return {"status": "already_authenticated"}

    if not Config.SIMKL_CLIENT_ID:
        raise HTTPException(status_code=503, detail="SIMKL_CLIENT_ID not configured")

    if _oauth_pending and _oauth_instance:
        return {"status": "pending", "auth_url": _oauth_instance.get_auth_url()}

    _oauth_instance = SimklOAuth(Config.SIMKL_CLIENT_ID, Config.SIMKL_TOKEN_FILE)
    try:
        _oauth_instance.start_callback_server()
    except OSError as e:
        _oauth_instance = None
        raise HTTPException(status_code=503, detail=f"Port 8888 occupé ({e}). Fermez l'autre application ou changez le port.")
    _oauth_pending = True

    def wait_and_exchange():
        global _oauth_pending
        token = _oauth_instance.wait_for_callback(timeout=300)
        _oauth_pending = False
        if token:
            logger.info("Simkl OAuth authentication successful")
        else:
            logger.error("Simkl OAuth authentication failed or timed out")

    threading.Thread(target=wait_and_exchange, daemon=True).start()

    return {"status": "pending", "auth_url": _oauth_instance.get_auth_url()}


# ============== Export ==============

@app.get("/api/export/csv")
async def export_csv(
    watched: bool = Query(True),
    watchlist: bool = Query(False),
):
    """Export movies to CSV format."""
    from io import StringIO
    import csv

    output = StringIO()
    writer = csv.writer(output)

    if watched:
        # Watched movies
        writer.writerow([
            "imdbID", "tmdbID", "Title", "Year", "Directors",
            "WatchedDate", "Rating", "Rewatch", "Tags", "Review"
        ])

        movies = db.get_all_movies(watched=True, limit=10000)
        for m in movies:
            writer.writerow([
                m.imdb_id or "",
                m.tmdb_id or "",
                m.title,
                m.year or "",
                m.directors or "",
                m.watched_date.isoformat() if m.watched_date else "",
                m.rating or "",
                "true" if m.rewatch else "false",
                m.tags or "",
                m.review or "",
            ])
    elif watchlist:
        # Watchlist
        writer.writerow(["imdbID", "tmdbID", "Title", "Year", "Directors"])

        movies = db.get_all_movies(watchlist=True, limit=10000)
        for m in movies:
            writer.writerow([
                m.imdb_id or "",
                m.tmdb_id or "",
                m.title,
                m.year or "",
                m.directors or "",
            ])

    from fastapi.responses import Response
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=letterboxd_{'watched' if watched else 'watchlist'}.csv"
        },
    )
