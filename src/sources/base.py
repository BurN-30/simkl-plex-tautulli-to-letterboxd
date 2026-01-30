"""Abstract base class for data sources."""

from abc import ABC, abstractmethod
from typing import List

from src.models import WatchEntry, WatchlistEntry


class BaseSource(ABC):
    """Abstract base class for movie data sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the source name."""
        pass

    @abstractmethod
    def get_watched(self) -> List[WatchEntry]:
        """
        Get list of watched movies.

        Returns:
            List of WatchEntry objects with movie data and watch info.
        """
        pass

    @abstractmethod
    def get_watchlist(self) -> List[WatchlistEntry]:
        """
        Get watchlist.

        Returns:
            List of WatchlistEntry objects.
        """
        pass

    def test_connection(self) -> bool:
        """
        Test if the source is accessible.

        Returns:
            True if connection is successful, False otherwise.
        """
        return True
