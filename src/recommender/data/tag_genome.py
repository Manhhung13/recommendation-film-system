"""Read-only, version-bound MovieLens Tag Genome ingestion.

Scores are streamed from CSV into packed per-movie double arrays. Memory is
O(movie IDs + tag vocabulary + genome movies * tag vocabulary), with no CSV
row list, pandas frame, or matrix of Python float objects.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isnan
from pathlib import Path
import re
import struct
from types import MappingProxyType
from typing import Mapping

from .id_mapping import _fingerprint
from .movielens import (
    DEFAULT_ROOT, DataValidationError, MovieLens, SourceRow, _integer, _text,
)

TAG_SCHEMA = ("tagId", "tag")
SCORE_SCHEMA = ("movieId", "tagId", "relevance")
DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class GenomeMovie:
    movie_id: int
    packed_relevance: bytes
    observed_tags: int
    first_source: SourceRow
    last_source: SourceRow


@dataclass(frozen=True, slots=True)
class TagGenome:
    source_version: str
    movie_ids: frozenset[int]
    tag_ids: tuple[int, ...]
    tags: Mapping[int, str]
    tag_positions: Mapping[int, int]
    tag_sources: Mapping[int, SourceRow]
    movies: Mapping[int, GenomeMovie]
    missing_movie_ids: tuple[int, ...]
    incomplete_movie_ids: tuple[int, ...]
    stats: Mapping[str, int | float]
    sources: Mapping[str, Mapping[str, int | str]]

    def relevance(self, movie_id: int, tag_id: int) -> float | None:
        """Return None for missing movies or omitted scores in an audit vector."""
        if movie_id not in self.movie_ids:
            raise KeyError(movie_id)
        try:
            position = self.tag_positions[tag_id]
        except KeyError:
            raise KeyError(tag_id) from None
        movie = self.movies.get(movie_id)
        if movie is None:
            return None
        value = struct.unpack_from("=d", movie.packed_relevance, position * 8)[0]
        return None if isnan(value) else value


def _relevance(text: str, source: SourceRow) -> float:
    if len(text) > 128 or not DECIMAL.fullmatch(text):
        raise DataValidationError("invalid_relevance", source, "relevance")
    try:
        exact = Decimal(text)
    except InvalidOperation:
        raise DataValidationError("invalid_relevance", source, "relevance") from None
    if not Decimal(0) <= exact <= Decimal(1):
        raise DataValidationError("invalid_relevance", source, "relevance")
    return float(exact)


def load_tag_genome(root: str | Path = DEFAULT_ROOT, *,
                    source_version: str = "ml-25m",
                    strict_complete: bool = True) -> TagGenome:
    """Align tagId-indexed scores to MovieLens movieId, without changing raw data.

    Missing movies are explicit. A present movie with fewer than every known
    tag is rejected by default; callers auditing incomplete data can opt in to
    a partial result where omitted scores resolve to None.
    """
    if not source_version or not source_version.strip():
        raise ValueError("source_version must be nonempty")
    data = MovieLens(root)
    paths = [data.root / name for name in
             ("movies.csv", "genome-tags.csv", "genome-scores.csv")]
    before = {str(path): _fingerprint(path) for path in paths}
    movie_ids = {movie.movie_id for movie in data.movies()}
    if not movie_ids:
        raise DataValidationError("empty_table", SourceRow(str(paths[0]), 1, 1, 1), "record")

    tag_text: dict[int, str] = {}
    tag_sources: dict[int, SourceRow] = {}
    for row, source in data._rows("genome-tags.csv", expected=TAG_SCHEMA):
        tag_id = _integer(row[0], source, "tagId")
        label = _text(row[1], source, "tag")
        if tag_id in tag_text:
            raise DataValidationError("duplicate_tagId", source, "tagId")
        tag_text[tag_id] = label
        tag_sources[tag_id] = source
    if not tag_text:
        raise DataValidationError("empty_table", SourceRow(str(paths[1]), 1, 1, 1), "record")
    tag_ids = tuple(sorted(tag_text))
    positions = {tag_id: i for i, tag_id in enumerate(tag_ids)}
    count = len(tag_ids)

    values: dict[int, array] = {}
    observed: dict[int, int] = {}
    first: dict[int, SourceRow] = {}
    last: dict[int, SourceRow] = {}
    score_rows = 0
    for row, source in data._rows("genome-scores.csv", expected=SCORE_SCHEMA):
        movie_id = _integer(row[0], source, "movieId")
        tag_id = _integer(row[1], source, "tagId")
        score = _relevance(row[2], source)
        if movie_id not in movie_ids:
            raise DataValidationError("unknown_movieId", source, "movieId")
        if tag_id not in positions:
            raise DataValidationError("unknown_tagId", source, "tagId")
        if movie_id not in values:
            values[movie_id] = array("d", [float("nan")]) * count
            observed[movie_id] = 0
            first[movie_id] = source
        position = positions[tag_id]
        if not isnan(values[movie_id][position]):
            raise DataValidationError("duplicate_score", source, "tagId")
        values[movie_id][position] = score
        observed[movie_id] += 1
        last[movie_id] = source
        score_rows += 1
    if not score_rows:
        raise DataValidationError("empty_table", SourceRow(str(paths[2]), 1, 1, 1), "record")

    incomplete = tuple(sorted(movie for movie, total in observed.items() if total != count))
    if strict_complete and incomplete:
        movie = incomplete[0]
        raise DataValidationError("incomplete_vector", first[movie], "tagId")
    missing = tuple(sorted(movie_ids - values.keys()))
    packed = {}
    for movie in tuple(values):
        scores = values.pop(movie)
        packed[movie] = GenomeMovie(movie, scores.tobytes(), observed[movie],
                                    first[movie], last[movie])
    after = {str(path): _fingerprint(path) for path in paths}
    if before != after:
        raise DataValidationError("source_changed", SourceRow(str(data.root), 0, 0, 0), "file")
    stats = {"movies": len(movie_ids), "genome_movies": len(packed),
             "missing_movies": len(missing), "incomplete_movies": len(incomplete),
             "tags": count, "score_rows": score_rows,
             "movie_coverage": len(packed) / len(movie_ids)}
    return TagGenome(source_version, frozenset(movie_ids), tag_ids,
                     MappingProxyType(tag_text),
                     MappingProxyType(positions), MappingProxyType(tag_sources),
                     MappingProxyType(packed),
                     missing, incomplete, MappingProxyType(stats),
                     MappingProxyType({key: MappingProxyType(value)
                                       for key, value in after.items()}))
