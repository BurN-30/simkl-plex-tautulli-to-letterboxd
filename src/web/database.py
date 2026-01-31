"""Database models and operations using SQLAlchemy."""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class MovieDB(Base):
    """SQLAlchemy model for movies."""

    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, unique=True, nullable=True, index=True)
    imdb_id = Column(String(20), unique=True, nullable=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    year = Column(Integer, nullable=True)
    directors = Column(String(500), nullable=True)
    poster_url = Column(String(500), nullable=True)

    # Watch info
    watched_date = Column(Date, nullable=True)
    rating = Column(Float, nullable=True)  # 0.5-5.0 scale
    rewatch = Column(Boolean, default=False)
    tags = Column(String(500), nullable=True)
    review = Column(Text, nullable=True)

    # Status
    is_watched = Column(Boolean, default=True)
    is_watchlist = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
            "title": self.title,
            "year": self.year,
            "directors": self.directors,
            "poster_url": self.poster_url,
            "watched_date": self.watched_date.isoformat() if self.watched_date else None,
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


class Database:
    """Database operations."""

    def __init__(self, db_path: Path = Path("data/movies.db")):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

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

    def upsert_movie(self, movie_data: dict) -> MovieDB:
        """Insert or update a movie."""
        with self.get_session() as session:
            # Try to find existing movie
            existing = None
            if movie_data.get("tmdb_id"):
                existing = session.query(MovieDB).filter(
                    MovieDB.tmdb_id == movie_data["tmdb_id"]
                ).first()
            elif movie_data.get("imdb_id"):
                existing = session.query(MovieDB).filter(
                    MovieDB.imdb_id == movie_data["imdb_id"]
                ).first()

            if existing:
                # Update existing
                for key, value in movie_data.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                session.commit()
                session.refresh(existing)
                return existing
            else:
                # Create new
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

    def get_sync_status(self) -> Optional[SyncStatus]:
        """Get sync status."""
        with self.get_session() as session:
            status = session.query(SyncStatus).first()
            if not status:
                status = SyncStatus()
                session.add(status)
                session.commit()
            return status

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
