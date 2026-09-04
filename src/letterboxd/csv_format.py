r"""The Letterboxd CSV dialect: writer, reader and file splitting.

Letterboxd does **not** use RFC 4180 quoting. The official import page
(https://letterboxd.com/about/importing-data/) states:

    "Your CSV file must use the comma character (,) to delimit columns - do not
     include a space character immediately after the comma, as this can
     interfere with the parsing of quoted strings. Strings containing commas
     (such as film titles, director/tag lists or review text) must be placed
     inside quotes [...] Don't forget to escape quotes within quoted text, by
     prefixing them with a backslash (\) character."

A double quote inside a quoted field is therefore written ``\"`` and not ``""``.
Python's standard ``csv`` module can only produce the RFC 4180 doubling, which
Letterboxd's parser reads as two literal quotes, so this module implements the
dialect directly.

The same page also documents a hard 1 MB limit per uploaded file, with the
header row repeated in every part:

    "There is a file size limit of 1MB, so you'll need to divide large files
     into multiple smaller files (the header row containing column names must
     be in every file)."

Files are written as UTF-8 without BOM and with ``\n`` line endings.

Backslash handling
------------------
Letterboxd documents ``\"`` but says nothing about a literal backslash. This
module escapes backslashes as ``\\`` inside quoted fields, which keeps the
writer and the reader exactly reversible and, more importantly, prevents a
field ending in a backslash from swallowing its own closing quote. Backslashes
are close to nonexistent in film reviews, so the cosmetic risk (a parser that
does not unescape ``\\`` showing a doubled backslash) is preferred over a
possible parse break.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

DELIMITER = ","
QUOTE = '"'
ESCAPE = "\\"
LINE_TERMINATOR = "\n"

#: Hard limit enforced by the Letterboxd importer.
LETTERBOXD_MAX_FILE_BYTES = 1_000_000

#: Default split threshold, kept under the hard limit for safety margin.
DEFAULT_MAX_FILE_BYTES = 950_000

_SPECIAL_CHARS = (DELIMITER, QUOTE, ESCAPE, "\n", "\r")


def format_field(value: object) -> str:
    """Render a single value as a Letterboxd CSV field.

    Fields are quoted only when needed: when they contain the delimiter, a
    quote, a backslash, a line break, or leading/trailing whitespace (which the
    importer may otherwise fold into the neighbouring quoting).
    """
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    if not text:
        return ""

    needs_quotes = any(ch in text for ch in _SPECIAL_CHARS) or text != text.strip()
    if not needs_quotes:
        return text

    escaped = text.replace(ESCAPE, ESCAPE + ESCAPE).replace(QUOTE, ESCAPE + QUOTE)
    return f"{QUOTE}{escaped}{QUOTE}"


def format_row(values: Sequence[object]) -> str:
    """Render one CSV line (without the trailing line terminator)."""
    return DELIMITER.join(format_field(value) for value in values)


def render(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    """Render a complete CSV document as a string."""
    lines = [format_row(headers)]
    lines.extend(format_row(row) for row in rows)
    return LINE_TERMINATOR.join(lines) + LINE_TERMINATOR


def parse(text: str) -> list[list[str]]:
    """Parse a Letterboxd-dialect CSV document into rows of strings.

    This is the exact inverse of :func:`render` and is what ``confirm`` uses to
    read back a CSV file that was handed to Letterboxd.
    """
    rows: list[list[str]] = []
    row: list[str] = []
    field: list[str] = []
    in_quotes = False
    started_quoted = False
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if in_quotes:
            if char == ESCAPE and index + 1 < length:
                field.append(text[index + 1])
                index += 2
                continue
            if char == QUOTE:
                in_quotes = False
                index += 1
                continue
            field.append(char)
            index += 1
            continue

        if char == QUOTE and not field and not started_quoted:
            in_quotes = True
            started_quoted = True
            index += 1
            continue

        if char == DELIMITER:
            row.append("".join(field))
            field = []
            started_quoted = False
            index += 1
            continue

        if char in "\r\n":
            if char == "\r" and index + 1 < length and text[index + 1] == "\n":
                index += 1
            row.append("".join(field))
            rows.append(row)
            field = []
            row = []
            started_quoted = False
            index += 1
            continue

        field.append(char)
        index += 1

    if field or row or started_quoted:
        row.append("".join(field))
        rows.append(row)

    return rows


def parse_dicts(text: str) -> list[dict[str, str]]:
    """Parse a CSV document into dictionaries keyed by the header row."""
    rows = parse(text)
    if not rows:
        return []
    headers = rows[0]
    result = []
    for row in rows[1:]:
        if not any(cell for cell in row):
            continue
        padded = list(row) + [""] * (len(headers) - len(row))
        result.append(dict(zip(headers, padded)))
    return result


def _encoded_length(line: str) -> int:
    return len(line.encode("utf-8")) + len(LINE_TERMINATOR)


def split_rows(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> list[list[str]]:
    """Group rendered rows into chunks that each stay under ``max_bytes``.

    The header line is counted in every chunk. A single row larger than
    ``max_bytes`` is kept in a chunk of its own and reported: it cannot be
    split, and Letterboxd would reject it.
    """
    header_line = format_row(headers)
    header_size = _encoded_length(header_line)

    chunks: list[list[str]] = []
    current: list[str] = []
    current_size = header_size

    for row in rows:
        line = format_row(row)
        line_size = _encoded_length(line)

        if current and current_size + line_size > max_bytes:
            chunks.append(current)
            current = []
            current_size = header_size

        if not current and header_size + line_size > max_bytes:
            logger.warning(
                "A single CSV row is %d bytes, above the %d byte limit; "
                "Letterboxd will reject that file",
                line_size,
                max_bytes,
            )

        current.append(line)
        current_size += line_size

    if current:
        chunks.append(current)

    return chunks


def write_chunked(
    directory: Path,
    basename: str,
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> list[Path]:
    """Write rows to one or more CSV files under the Letterboxd size limit.

    Returns the paths written, in order. A single chunk is named
    ``<basename>.csv``; several chunks are named ``<basename>_part01.csv`` and
    so on. Nothing is written when there are no rows.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    header_line = format_row(headers)
    chunks = split_rows(headers, rows, max_bytes=max_bytes)
    if not chunks:
        return []

    paths: list[Path] = []
    for number, chunk in enumerate(chunks, start=1):
        if len(chunks) == 1:
            path = directory / f"{basename}.csv"
        else:
            path = directory / f"{basename}_part{number:02d}.csv"

        content = LINE_TERMINATOR.join([header_line, *chunk]) + LINE_TERMINATOR
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)

        paths.append(path)
        logger.debug("Wrote %s (%d rows, %d bytes)", path, len(chunk), path.stat().st_size)

    return paths
