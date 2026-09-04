"""Date handling for Letterboxd diary entries.

Letterboxd stores calendar dates, not timestamps
(https://letterboxd.com/about/importing-data/):

    "If your data contains timestamps, please truncate these to calendar date
     only (after performing any necessary time-zone conversion, such as from
     UTC to your local time zone)."

Plex and Tautulli hand out UTC timestamps, so they must be converted to the
local zone before truncation, otherwise an evening watch lands on the next day.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_zone_cache: dict[str, object] = {}


def get_zone(name: str):
    """Return a tzinfo for ``name``, falling back to UTC when unavailable."""
    if name in _zone_cache:
        return _zone_cache[name]
    zone: object = timezone.utc
    if ZoneInfo is not None:
        try:
            zone = ZoneInfo(name)
        except Exception as exc:  # pragma: no cover - depends on tzdata
            logger.warning("Timezone %s unavailable (%s), falling back to UTC", name, exc)
    _zone_cache[name] = zone
    return zone


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp, assuming UTC when no offset is given."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        logger.debug("Unparsable timestamp: %r", value)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def to_calendar_date(
    value: Optional[str],
    timezone_name: Optional[str] = None,
) -> Optional[date]:
    """Turn a timestamp into the calendar date to write in ``WatchedDate``.

    With ``timezone_name`` set, the timestamp is converted to that zone first;
    without it, the timestamp is truncated as-is (used for Simkl, whose bulk
    import markers are plain dates pinned to midnight UTC).
    """
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone_name:
        parsed = parsed.astimezone(get_zone(timezone_name))
    return parsed.date()


def epoch_to_calendar_date(value: Optional[float], timezone_name: str) -> Optional[date]:
    """Convert a Unix timestamp (Tautulli) to a local calendar date."""
    if not value:
        return None
    try:
        moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None
    return moment.astimezone(get_zone(timezone_name)).date()
