"""Strict MovieLens CSV readers. Standard library only; never writes source files.

Readers yield immutable rows in source order, without deduplication or sorting.
Blank tag text and absent external IDs are preserved, not silently discarded.
Referential checks are optional per iterator and mandatory in validate_movielens.
"""
from __future__ import annotations

from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import csv
import hashlib
from itertools import islice
import os
from pathlib import Path
from typing import TypeVar

DEFAULT_ROOT = Path("dataset_linkage_work/raw/movielens/ml-25m")
SCHEMAS = {
    "ratings.csv": ("userId", "movieId", "rating", "timestamp"),
    "movies.csv": ("movieId", "title", "genres"),
    "tags.csv": ("userId", "movieId", "tag", "timestamp"),
    "links.csv": ("movieId", "imdbId", "tmdbId"),
}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MAX_TIMESTAMP = 253402300799  # Last whole second of datetime year 9999, UTC.
MAX_ID = 2**63 - 1
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SourceRow:
    source_file: str
    record_number: int  # CSV header is record 1; multiline records count once.
    line_start: int
    line_end: int

    @property
    def key(self) -> tuple[str, int]:
        return self.source_file, self.record_number


class DataValidationError(ValueError):
    """Stable error code/field/location; never echoes raw user/tag values."""

    def __init__(self, code: str, source: SourceRow, field: str):
        self.code, self.source, self.field = code, source, field
        super().__init__(
            f"{Path(source.source_file).name}:record={source.record_number}:"
            f"lines={source.line_start}-{source.line_end}:{field}:{code}"
        )


@dataclass(frozen=True, slots=True)
class Rating:
    user_id: int
    movie_id: int
    rating: float
    timestamp: datetime
    source: SourceRow


@dataclass(frozen=True, slots=True)
class Movie:
    movie_id: int
    title: str
    genres: tuple[str, ...]
    source: SourceRow


@dataclass(frozen=True, slots=True)
class Tag:
    user_id: int
    movie_id: int
    tag: str
    timestamp: datetime
    source: SourceRow


@dataclass(frozen=True, slots=True)
class Link:
    movie_id: int
    imdb_id: str | None  # Preserve leading zeros; mapping is DATA-002.
    tmdb_id: int | None
    source: SourceRow


def _integer(value: str, source: SourceRow, field: str, *, minimum=1,
             maximum=MAX_ID, code="invalid_id") -> int:
    significant = value.lstrip("0") or "0"
    if (not value or not value.isascii() or not value.isdecimal()
            or len(significant) > len(str(maximum))):
        raise DataValidationError(code, source, field)
    number = int(significant)
    if not minimum <= number <= maximum:
        raise DataValidationError(code, source, field)
    return number


def _timestamp(value: str, source: SourceRow) -> datetime:
    seconds = _integer(value, source, "timestamp", minimum=0,
                       maximum=MAX_TIMESTAMP, code="invalid_timestamp")
    # No platform-local timezone or Windows C-runtime timestamp conversion.
    return EPOCH + timedelta(seconds=seconds)


def _rating(value: str, source: SourceRow) -> float:
    digits = value.replace(".", "", 1)
    if not digits or not digits.isascii() or not digits.isdecimal() or len(value) > 32:
        raise DataValidationError("invalid_rating", source, "rating")
    whole, _, fraction = value.partition(".")
    fraction = fraction.rstrip("0")
    integer = int(whole or "0")
    # Validate decimal text before float conversion: near-half values must not
    # round into an allowed rating (e.g. 4.50000000000000000001).
    if fraction not in ("", "5") or integer > 5:
        raise DataValidationError("invalid_rating", source, "rating")
    number = integer + (0.5 if fraction == "5" else 0.0)
    if not 0.5 <= number <= 5.0:
        raise DataValidationError("invalid_rating", source, "rating")
    return number


def _text(value: str, source: SourceRow, field: str, *, allow_blank=False) -> str:
    if "\0" in value or (not allow_blank and not value.strip()):
        raise DataValidationError("invalid_text", source, field)
    return value


def _reference(value: int, known: Collection[int] | None, source: SourceRow,
               field: str) -> None:
    if known is not None and value not in known:
        raise DataValidationError("unknown_" + field, source, field)


def _signature(stat: os.stat_result) -> tuple[int, int, int, int]:
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


class MovieLens:
    """Reusable source directory; each iterator opens its own read-only stream.

    Exhaust or explicitly close iterators to release handles promptly. Only
    movies/links retain a set of movie IDs for uniqueness. Ratings/tags do not
    retain event rows or user/movie pairs. No user identity is joined externally.
    """

    def __init__(self, root: str | Path = DEFAULT_ROOT):
        self.root = Path(root).resolve()

    def _rows(self, table: str, *, expected: tuple[str, ...] | None = None
              ) -> Iterator[tuple[list[str], SourceRow]]:
        path = self.root / table
        expected = SCHEMAS[table] if expected is None else expected
        source = SourceRow(str(path), 1, 1, 1)
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                initial = _signature(os.fstat(handle.fileno()))
                reader = csv.reader(handle, strict=True)
                try:
                    header = next(reader, None)
                    if (header is None or len(header) != len(expected)
                            or set(header) != set(expected)):
                        raise DataValidationError("schema", source, "header")
                    positions = [header.index(name) for name in expected]
                    record_number = 1
                    while True:
                        source = SourceRow(str(path), record_number + 1,
                                           reader.line_num + 1, reader.line_num + 1)
                        row = next(reader, None)
                        if row is None:
                            break
                        record_number += 1
                        source = SourceRow(str(path), record_number, source.line_start, reader.line_num)
                        if len(row) != len(expected):
                            raise DataValidationError("row_width", source, "record")
                        yield [row[position] for position in positions], source
                except csv.Error:
                    source = SourceRow(str(path), source.record_number, source.line_start,
                                       max(source.line_start, reader.line_num))
                    raise DataValidationError("csv_syntax", source, "record") from None
                finally:
                    if initial != _signature(path.stat()):
                        raise DataValidationError("source_changed", source, "file")
        except UnicodeError:
            raise DataValidationError("encoding", source, "record") from None
        except OSError:
            raise DataValidationError("source_unavailable", source, "file") from None

    def ratings(self, *, movie_ids: Collection[int] | None = None) -> Iterator[Rating]:
        for row, source in self._rows("ratings.csv"):
            user = _integer(row[0], source, "userId")
            movie = _integer(row[1], source, "movieId")
            rating = _rating(row[2], source)
            timestamp = _timestamp(row[3], source)
            _reference(movie, movie_ids, source, "movieId")
            yield Rating(user, movie, rating, timestamp, source)

    def movies(self) -> Iterator[Movie]:
        seen = set()
        for row, source in self._rows("movies.csv"):
            movie = _integer(row[0], source, "movieId")
            title = _text(row[1], source, "title")
            genres = tuple(_text(row[2], source, "genres").split("|"))
            if any(not genre.strip() for genre in genres):
                raise DataValidationError("invalid_text", source, "genres")
            if movie in seen:
                raise DataValidationError("duplicate_movieId", source, "movieId")
            seen.add(movie)
            yield Movie(movie, title, genres, source)

    def tags(self, *, movie_ids: Collection[int] | None = None,
             user_ids: Collection[int] | None = None) -> Iterator[Tag]:
        for row, source in self._rows("tags.csv"):
            user = _integer(row[0], source, "userId")
            movie = _integer(row[1], source, "movieId")
            tag = _text(row[2], source, "tag", allow_blank=True)
            timestamp = _timestamp(row[3], source)
            _reference(movie, movie_ids, source, "movieId")
            _reference(user, user_ids, source, "userId")
            yield Tag(user, movie, tag, timestamp, source)

    def links(self, *, movie_ids: Collection[int] | None = None) -> Iterator[Link]:
        seen = set()
        for row, source in self._rows("links.csv"):
            movie = _integer(row[0], source, "movieId")
            imdb = None if row[1] == "" else row[1]
            if imdb is not None:
                _integer(imdb, source, "imdbId")
            tmdb = None if row[2] == "" else _integer(row[2], source, "tmdbId")
            _reference(movie, movie_ids, source, "movieId")
            if movie in seen:
                raise DataValidationError("duplicate_movieId", source, "movieId")
            seen.add(movie)
            yield Link(movie, imdb, tmdb, source)


def batches(rows: Iterable[T], size: int = 100_000) -> Iterator[tuple[T, ...]]:
    """Bound memory to at most size rows; close an owned generator on exit."""
    if type(size) is not int or size < 1:
        raise ValueError("batch size must be a positive integer")
    iterator = iter(rows)
    try:
        while batch := tuple(islice(iterator, size)):
            yield batch
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            close()


def source_snapshot(root: str | Path = DEFAULT_ROOT) -> dict[str, dict]:
    """Streaming SHA-256 and stat inventory of exactly the four raw tables."""
    root = Path(root).resolve()
    result = {}
    for table in SCHEMAS:
        path = root / table
        source = SourceRow(str(path), 0, 0, 0)
        try:
            before = _signature(path.stat())
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                if before != _signature(os.fstat(handle.fileno())):
                    raise DataValidationError("source_changed", source, "file")
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            if before != _signature(path.stat()):
                raise DataValidationError("source_changed", source, "file")
        except OSError:
            raise DataValidationError("source_unavailable", source, "file") from None
        result[table] = {"sha256": hasher.hexdigest(), "size_bytes": before[2], "mtime_ns": before[3]}
    return result


def validate_movielens(root: str | Path = DEFAULT_ROOT) -> dict:
    """Scan ALL rows with O(movie IDs + user IDs) memory, preserving raw bytes.

    Check movie key uniqueness, links completeness, all event movie references,
    and tag users against the observed rating-user population. No global event
    deduplication, temporal split, cross-dataset join or DATA-QUALITY certification.
    """
    data = MovieLens(root)
    before = source_snapshot(data.root)
    movie_ids = {movie.movie_id for movie in data.movies()}
    linked = set()
    missing_imdb = missing_tmdb = 0
    for link in data.links(movie_ids=movie_ids):
        linked.add(link.movie_id)
        missing_imdb += link.imdb_id is None
        missing_tmdb += link.tmdb_id is None
    if movie_ids != linked:
        raise DataValidationError("missing_movie_link", SourceRow(str(data.root / "links.csv"), 1, 1, 1), "movieId")
    user_ids = set()
    rating_count = tag_count = blank_tags = 0
    rating_min = rating_max = tag_min = tag_max = None
    for rating in data.ratings(movie_ids=movie_ids):
        rating_count += 1
        user_ids.add(rating.user_id)
        stamp = rating.timestamp
        if rating_min is None or stamp < rating_min: rating_min = stamp
        if rating_max is None or stamp > rating_max: rating_max = stamp
    for tag in data.tags(movie_ids=movie_ids, user_ids=user_ids):
        tag_count += 1
        blank_tags += not tag.tag.strip()
        stamp = tag.timestamp
        if tag_min is None or stamp < tag_min: tag_min = stamp
        if tag_max is None or stamp > tag_max: tag_max = stamp
    counts = {"movies.csv": len(movie_ids), "links.csv": len(linked),
              "ratings.csv": rating_count, "tags.csv": tag_count}
    for table, count in counts.items():
        if count == 0:
            raise DataValidationError("empty_table", SourceRow(str(data.root / table), 1, 1, 1), "record")
    after = source_snapshot(data.root)
    if before != after:
        raise DataValidationError("source_changed", SourceRow(str(data.root), 0, 0, 0), "file")
    return {
        "schema_version": 1, "scope": "DATA-001 MovieLens raw table loading only",
        "scan": "FULL", "status": "PASS", "source_unchanged": True,
        "rows": counts, "rating_users": len(user_ids), "blank_tag_rows": blank_tags,
        "missing_imdb_ids": missing_imdb, "missing_tmdb_ids": missing_tmdb,
        "rating_timestamp_utc": {"min": rating_min.isoformat(), "max": rating_max.isoformat()},
        "tag_timestamp_utc": {"min": tag_min.isoformat(), "max": tag_max.isoformat()},
        "sources": after,
    }
