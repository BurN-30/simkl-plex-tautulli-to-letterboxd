"""Database models and operations using SQLAlchemy."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the naive DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class SyncSummary:
    """Detached snapshot of :class:`SyncStatus`, safe to read after commit."""

    last_sync: Optional[datetime] = None
    movies_count: int = 0
    watchlist_count: int = 0
    status: str = "idle"
    error_message: Optional[str] = None
    last_export: Optional[datetime] = None
    last_confirm: Optional[datetime] = None

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.models import Movie, WatchEntry, WatchlistEntry, normalize_tags


class Base(DeclarativeBase):
    pass


class MovieDB(Base):
    """SQLAlchemy model for movies."""

    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, unique=True, nullable=True, index=True)
    imdb_id = Column(String(20), unique=True, nullable=True, index=True)
    simkl_id = Column(Integer, unique=True, nullable=True, index=True)
    letterboxd_slug = Column(String(200), nullable=True)
    title = Column(String(500), nullable=False, index=True)
    year = Column(Integer, nullable=True)
    directors = Column(String(500), nullable=True)
    poster_url = Column(String(500), nullable=True)

    # Watch info
    watched_date = Column(Date, nullable=True)
    # rating10 (1-10) is what Simkl gives and what the CSV exports; rating
    # (0.5-5.0) is derived from it for the dashboard and the statistics.
    rating10 = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)
    rewatch = Column(Boolean, default=False)
    tags = Column(String(500), nullable=True)
    review = Column(Text, nullable=True)

    # Status
    is_watched = Column(Boolean, default=True)
    is_watchlist = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    source = Column(String(50), default="simkl")

    @property
    def letterboxd_url(self) -> Optional[str]:
        """Generate Letterboxd URL."""
        if self.tmdb_id:
            return f"https://letterboxd.com/tmdb/{self.tmdb_id}/"
        return None

    @property
    def tmdb_url(self) -> Optional[str]:
        """Generate TMDB URL."""
        if self.tmdb_id:
            return f"https://www.themoviedb.org/movie/{self.tmdb_id}"
        return None

    @property
    def imdb_url(self) -> Optional[str]:
        """Generate IMDB URL."""
        if self.imdb_id:
            return f"https://www.imdb.com/title/{self.imdb_id}/"
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "imdb_id": self.imdb_id,
            "simkl_id": self.simkl_id,
            "letterboxd_slug": self.letterboxd_slug,
            "title": self.title,
            "year": self.year,
            "directors": self.directors,
            "poster_url": self.poster_url,
            "watched_date": self.watched_date.isoformat() if self.watched_date else None,
            "rating10": self.rating10,
            "rating": self.rating,
            "rewatch": self.rewatch,
            "tags": self.tags,
            "review": self.review,
            "is_watched": self.is_watched,
            "is_watchlist": self.is_watchlist,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "source": self.source,
            "letterboxd_url": self.letterboxd_url,
            "tmdb_url": self.tmdb_url,
            "imdb_url": self.imdb_url,
        }


class SyncStatus(Base):
    """Track sync status."""

    __tablename__ = "sync_status"

    id = Column(Integer, primary_key=True)
    last_sync = Column(DateTime, nullable=True)
    movies_count = Column(Integer, default=0)
    watchlist_count = Column(Integer, default=0)
    status = Column(String(50), default="idle")  # idle, syncing, error
    error_message = Column(Text, nullable=True)
    last_export = Column(DateTime, nullable=True)
    last_confirm = Column(DateTime, nullable=True)


class ExportState(Base):
    """Last confirmed state of a Letterboxd diary entry.

    One row per importable entry, keyed on (film, WatchedDate) because that is
    exactly the pair the Letterboxd importer matches on when it decides to
    update an existing diary entry instead of creating one.

    ``fingerprint`` is the hash of the user data (rating, review, rewatch,
    tags) as it was in the CSV file that was confirmed as imported. An entry is
    "pending" when it has no row here, or when its current fingerprint differs
    from the stored one.
    """

    __tablename__ = "export_state"
    __table_args__ = (UniqueConstraint("film_key", "watched_date", name="uq_export_entry"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    film_key = Column(String(200), nullable=False, index=True)
    #  Empty string for an entry without a watch date (rating-only line).
    watched_date = Column(String(10), nullable=False, default="")
    fingerprint = Column(String(64), nullable=False)
    confirmed_at = Column(DateTime, nullable=False, default=utcnow)
    source_file = Column(String(300), nullable=True)


class Database:
    """Database operations."""

    def __init__(self, db_path: Path = Path("data/movies.db")):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self._migrate()
        self.SessionLocal = sessionmaker(bind=self.engine)

    def _migrate(self) -> None:
        """Add columns introduced after a database was first created.

        SQLite cannot alter a table in place beyond adding columns, which is
        all this schema has ever needed.
        """
        inspector = inspect(self.engine)
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                column_type = column.type.compile(self.engine.dialect)
                with self.engine.begin() as connection:
                    connection.execute(
                        text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {column_type}')
                    )

    def get_session(self) -> Session:
        return self.SessionLocal()

    def close(self) -> None:
        """Release the SQLite file handle (Windows keeps it locked otherwise)."""
        self.engine.dispose()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def get_all_movies(
        self,
        watched: Optional[bool] = None,
        watchlist: Optional[bool] = None,
        search: Optional[str] = None,
        year: Optional[int] = None,
        min_rating: Optional[float] = None,
        max_rating: Optional[float] = None,
        sort_by: str = "watched_date",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> list[MovieDB]:
        """Get movies with filters."""
        with self.get_session() as session:
            query = session.query(MovieDB)

            if watched is not None:
                query = query.filter(MovieDB.is_watched == watched)
            if watchlist is not None:
                query = query.filter(MovieDB.is_watchlist == watchlist)
            if search:
                query = query.filter(MovieDB.title.ilike(f"%{search}%"))
            if year:
                query = query.filter(MovieDB.year == year)
            if min_rating is not None:
                query = query.filter(MovieDB.rating >= min_rating)
            if max_rating is not None:
                query = query.filter(MovieDB.rating <= max_rating)

            # Sorting
            sort_column = getattr(MovieDB, sort_by, MovieDB.watched_date)
            if sort_order == "desc":
                query = query.order_by(sort_column.desc().nullslast())
            else:
                query = query.order_by(sort_column.asc().nullsfirst())

            return query.offset(offset).limit(limit).all()

    def get_movie_by_id(self, movie_id: int) -> Optional[MovieDB]:
        """Get a single movie by ID."""
        with self.get_session() as session:
            return session.query(MovieDB).filter(MovieDB.id == movie_id).first()

    def get_movie_by_tmdb_id(self, tmdb_id: int) -> Optional[MovieDB]:
        """Get a movie by TMDB ID."""
        with self.get_session() as session:
            return session.query(MovieDB).filter(MovieDB.tmdb_id == tmdb_id).first()

    def find_movie(self, session: Session, movie_data: dict) -> Optional[MovieDB]:
        """Locate an existing row for a movie, by id then by title and year."""
        for column, key in (
            (MovieDB.simkl_id, "simkl_id"),
            (MovieDB.tmdb_id, "tmdb_id"),
            (MovieDB.imdb_id, "imdb_id"),
        ):
            value = movie_data.get(key)
            if value:
                found = session.query(MovieDB).filter(column == value).first()
                if found:
                    return found

        title = movie_data.get("title")
        if title:
            return (
                session.query(MovieDB)
                .filter(
                    MovieDB.title == title,
                    MovieDB.year == movie_data.get("year"),
                    MovieDB.tmdb_id.is_(None),
                    MovieDB.imdb_id.is_(None),
                )
                .first()
            )
        return None

    def upsert_movie(self, movie_data: dict, protect_user_fields: bool = True) -> MovieDB:
        """Insert or update a movie.

        ``protect_user_fields`` keeps the review, tags and rewatch flag typed in
        the dashboard from being wiped by a sync, since no source provides them.
        """
        protected = {"review", "tags", "rewatch"} if protect_user_fields else set()

        with self.get_session() as session:
            existing = self.find_movie(session, movie_data)

            if existing:
                for key, value in movie_data.items():
                    if not hasattr(existing, key):
                        continue
                    if key in protected:
                        continue
                    if value is None and key not in {"rating10", "rating", "watched_date"}:
                        continue
                    setattr(existing, key, value)
                session.commit()
                session.refresh(existing)
                return existing

            movie = MovieDB(**movie_data)
            session.add(movie)
            session.commit()
            session.refresh(movie)
            return movie

    def update_movie(self, movie_id: int, updates: dict) -> Optional[MovieDB]:
        """Update a movie by ID."""
        with self.get_session() as session:
            movie = session.query(MovieDB).filter(MovieDB.id == movie_id).first()
            if movie:
                for key, value in updates.items():
                    if hasattr(movie, key):
                        setattr(movie, key, value)
                session.commit()
                session.refresh(movie)
                return movie
            return None

    def delete_movie(self, movie_id: int) -> bool:
        """Delete a movie by ID."""
        with self.get_session() as session:
            movie = session.query(MovieDB).filter(MovieDB.id == movie_id).first()
            if movie:
                session.delete(movie)
                session.commit()
                return True
            return False

    def get_statistics(self) -> dict:
        """Get statistics about the movie collection."""
        with self.get_session() as session:
            total_watched = session.query(MovieDB).filter(MovieDB.is_watched == True).count()
            total_watchlist = session.query(MovieDB).filter(MovieDB.is_watchlist == True).count()

            # Rating distribution
            rating_dist = {}
            for rating in [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5]:
                count = session.query(MovieDB).filter(
                    MovieDB.rating == rating,
                    MovieDB.is_watched == True
                ).count()
                rating_dist[str(rating)] = count

            # Movies by year
            movies_by_year = (
                session.query(MovieDB.year, func.count(MovieDB.id))
                .filter(MovieDB.is_watched == True, MovieDB.year.isnot(None))
                .group_by(MovieDB.year)
                .order_by(MovieDB.year.desc())
                .limit(20)
                .all()
            )

            # Movies by watch month
            movies_by_month = (
                session.query(
                    func.strftime("%Y-%m", MovieDB.watched_date),
                    func.count(MovieDB.id)
                )
                .filter(MovieDB.is_watched == True, MovieDB.watched_date.isnot(None))
                .group_by(func.strftime("%Y-%m", MovieDB.watched_date))
                .order_by(func.strftime("%Y-%m", MovieDB.watched_date).desc())
                .limit(12)
                .all()
            )

            # Average rating
            avg_rating = session.query(func.avg(MovieDB.rating)).filter(
                MovieDB.is_watched == True,
                MovieDB.rating.isnot(None)
            ).scalar()

            return {
                "total_watched": total_watched,
                "total_watchlist": total_watchlist,
                "average_rating": round(avg_rating, 2) if avg_rating else 0,
                "rating_distribution": rating_dist,
                "movies_by_year": {str(y): c for y, c in movies_by_year if y},
                "movies_by_month": {m: c for m, c in movies_by_month if m},
            }

    def get_sync_status(self) -> SyncSummary:
        """Read the sync status as a detached snapshot.

        Returning the ORM instance itself would raise ``DetachedInstanceError``
        once the session closes, so the values are copied out.
        """
        with self.get_session() as session:
            status = session.query(SyncStatus).first()
            if not status:
                status = SyncStatus()
                session.add(status)
                session.commit()
                session.refresh(status)
            return SyncSummary(
                last_sync=status.last_sync,
                movies_count=status.movies_count or 0,
                watchlist_count=status.watchlist_count or 0,
                status=status.status or "idle",
                error_message=status.error_message,
                last_export=status.last_export,
                last_confirm=status.last_confirm,
            )

    def update_sync_status(self, **kwargs) -> None:
        """Update sync status."""
        with self.get_session() as session:
            status = session.query(SyncStatus).first()
            if not status:
                status = SyncStatus()
                session.add(status)

            for key, value in kwargs.items():
                if hasattr(status, key):
                    setattr(status, key, value)

            session.commit()

    def get_years(self) -> list[int]:
        """Get list of unique years."""
        with self.get_session() as session:
            years = (
                session.query(MovieDB.year)
                .filter(MovieDB.year.isnot(None))
                .distinct()
                .order_by(MovieDB.year.desc())
                .all()
            )
            return [y[0] for y in years]

    def count_movies(
        self,
        watched: Optional[bool] = None,
        watchlist: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count movies with filters."""
        with self.get_session() as session:
            query = session.query(func.count(MovieDB.id))

            if watched is not None:
                query = query.filter(MovieDB.is_watched == watched)
            if watchlist is not None:
                query = query.filter(MovieDB.is_watchlist == watchlist)
            if search:
                query = query.filter(MovieDB.title.ilike(f"%{search}%"))

            return query.scalar() or 0

    # ---------------------------------------------------------------- entries

    def _row_to_movie(self, row: MovieDB) -> Movie:
        return Movie(
            title=row.title,
            year=row.year,
            tmdb_id=row.tmdb_id,
            imdb_id=row.imdb_id,
            simkl_id=row.simkl_id,
            letterboxd_slug=row.letterboxd_slug,
            directors=normalize_tags(row.directors),
        )

    def get_watch_entries(self) -> list[WatchEntry]:
        """Every watched film in the database, as exportable entries."""
        with self.get_session() as session:
            rows = (
                session.query(MovieDB)
                .filter(MovieDB.is_watched.is_(True))
                .order_by(MovieDB.watched_date.asc().nullsfirst(), MovieDB.title.asc())
                .all()
            )
            return [
                WatchEntry(
                    movie=self._row_to_movie(row),
                    watched_date=row.watched_date,
                    rating10=row.rating10,
                    rewatch=bool(row.rewatch),
                    tags=normalize_tags(row.tags),
                    review=row.review,
                )
                for row in rows
            ]

    def get_watchlist_entries(self) -> list[WatchlistEntry]:
        """Every watchlist film in the database."""
        with self.get_session() as session:
            rows = (
                session.query(MovieDB)
                .filter(MovieDB.is_watchlist.is_(True))
                .order_by(MovieDB.title.asc())
                .all()
            )
            return [WatchlistEntry(movie=self._row_to_movie(row)) for row in rows]

    # ----------------------------------------------------------- export state

    def get_export_state(self) -> dict[tuple[str, str], str]:
        """Map (film key, watched date) to the last confirmed fingerprint."""
        with self.get_session() as session:
            return {
                (row.film_key, row.watched_date or ""): row.fingerprint
                for row in session.query(ExportState).all()
            }

    def mark_confirmed(
        self,
        records: list[tuple[str, str, str]],
        source_file: Optional[str] = None,
    ) -> tuple[int, int]:
        """Record entries as imported. Returns (inserted, updated)."""
        inserted = 0
        updated = 0
        now = utcnow()

        with self.get_session() as session:
            for film_key, watched_date, fingerprint in records:
                watched_date = watched_date or ""
                existing = (
                    session.query(ExportState)
                    .filter(
                        ExportState.film_key == film_key,
                        ExportState.watched_date == watched_date,
                    )
                    .first()
                )
                if existing:
                    existing.fingerprint = fingerprint
                    existing.confirmed_at = now
                    existing.source_file = source_file
                    updated += 1
                else:
                    session.add(
                        ExportState(
                            film_key=film_key,
                            watched_date=watched_date,
                            fingerprint=fingerprint,
                            confirmed_at=now,
                            source_file=source_file,
                        )
                    )
                    inserted += 1
            session.commit()

        self.update_sync_status(last_confirm=now)
        return inserted, updated

    def count_export_state(self) -> int:
        with self.get_session() as session:
            return session.query(func.count(ExportState.id)).scalar() or 0

