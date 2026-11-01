"""Read-only MovieLens movie ID bridge to the existing IMDb and TMDb snapshots.

Only declared identifiers participate in joins. External snapshots have no
historical availability guarantee; this module never builds temporal features.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from .movielens import DEFAULT_ROOT, DataValidationError, MovieLens, SourceRow

DEFAULT_IMDB = Path("dataset_linkage_work/raw/imdb/title.basics.tsv.gz")
DEFAULT_TMDB = Path("dataset_linkage_work/raw/tmdb/movie_details.jsonl")
TCONST = re.compile(r"tt[0-9]+\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class MovieIdRecord:
    movie_id: int
    imdb_id: str | None
    imdb_tconst: str | None
    tmdb_id: int | None
    movie_source: SourceRow
    link_source: SourceRow
    imdb_metadata_source: SourceRow | None
    tmdb_metadata_source: SourceRow | None
    imdb_conflict: bool
    tmdb_conflict: bool


@dataclass(frozen=True, slots=True)
class MappingIssue:
    code: str
    source: SourceRow
    movie_ids: tuple[int, ...]
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class MovieIdMapping:
    records: Mapping[int, MovieIdRecord]
    stats: Mapping[str, int | float]
    issues: tuple[MappingIssue, ...]
    unmatched_imdb_ids: tuple[str, ...]
    unmatched_tmdb_ids: tuple[int, ...]
    sources: Mapping[str, Mapping[str, int | str]]

    def __getitem__(self, movie_id: int) -> MovieIdRecord:
        return self.records[movie_id]


def normalize_imdb_id(imdb_id: str | None) -> str | None:
    """Preserve source digits separately; IMDb tconst is padded to at least 7."""
    if imdb_id is None:
        return None
    if (not imdb_id or not imdb_id.isascii() or not imdb_id.isdecimal()
            or not imdb_id.strip("0")):
        raise ValueError("invalid IMDb numeric ID")
    return "tt" + imdb_id.zfill(7)


def _fingerprint(path: Path) -> dict[str, int | str]:
    source = SourceRow(str(path), 0, 0, 0)
    try:
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_size, opened.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                raise DataValidationError("source_changed", source, "file")
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        after = path.stat()
        if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise DataValidationError("source_changed", source, "file")
    except OSError:
        raise DataValidationError("source_unavailable", source, "file") from None
    return {"sha256": digest.hexdigest(), "size_bytes": before.st_size,
            "mtime_ns": before.st_mtime_ns}


def _imdb_rows(path: Path, targets: set[str]) -> tuple[dict[str, SourceRow], set[str]]:
    found: dict[str, SourceRow] = {}
    duplicates: set[str] = set()
    source = SourceRow(str(path), 1, 1, 1)
    try:
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            header_line = handle.readline()
            header = header_line.rstrip("\r\n").split("\t") if header_line else []
            if not header or len(header) != len(set(header)) or "tconst" not in header:
                raise DataValidationError("schema", source, "header")
            position = header.index("tconst")
            # IMDb is literal TSV: quotes in titles are data, not CSV quoting.
            for record, line in enumerate(handle, 2):
                source = SourceRow(str(path), record, record, record)
                row = line.rstrip("\r\n").split("\t")
                if len(row) != len(header):
                    raise DataValidationError("row_width", source, "record")
                key = row[position]
                if not TCONST.fullmatch(key):
                    raise DataValidationError("invalid_imdb_id", source, "tconst")
                if key in targets:
                    if key in found:
                        duplicates.add(key)
                    else:
                        found[key] = source
    except (OSError, EOFError):
        raise DataValidationError("source_unavailable", source, "file") from None
    except UnicodeError:
        raise DataValidationError("encoding", source, "record") from None
    return found, duplicates


def _positive_json_id(value: object, source: SourceRow, field: str) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise DataValidationError("invalid_id", source, field)
    return value


def _tmdb_rows(path: Path, links_by_movie: Mapping[int, object],
               target_ids: set[int]) -> tuple[dict[int, SourceRow], set[int], list[MappingIssue]]:
    found: dict[int, SourceRow] = {}
    duplicates: set[int] = set()
    bad: set[int] = set()
    issues: list[MappingIssue] = []
    source = SourceRow(str(path), 0, 0, 0)
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, 1):
                source = SourceRow(str(path), line_number, line_number, line_number)
                try:
                    envelope = json.loads(line)
                except json.JSONDecodeError:
                    raise DataValidationError("json_syntax", source, "record") from None
                if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), dict):
                    raise DataValidationError("schema", source, "data")
                movie_id = _positive_json_id(envelope.get("movieId"), source, "movieId")
                tmdb_id = _positive_json_id(envelope.get("tmdbId"), source, "tmdbId")
                provider_id = _positive_json_id(envelope["data"].get("id"), source, "data.id")
                raw_imdb = envelope.get("imdbId")
                if raw_imdb is not None:
                    _positive_json_id(raw_imdb, source, "imdbId")
                provider_imdb = envelope["data"].get("imdb_id")
                if provider_imdb in (None, ""):
                    provider_imdb = None
                elif not isinstance(provider_imdb, str) or not TCONST.fullmatch(provider_imdb):
                    raise DataValidationError("invalid_imdb_id", source, "data.imdb_id")
                if tmdb_id not in target_ids:
                    issues.append(MappingIssue("unmatched_tmdb_envelope", source, (movie_id,), str(tmdb_id)))
                    continue
                if tmdb_id in found:
                    duplicates.add(tmdb_id)
                    issues.append(MappingIssue("duplicate_tmdb_metadata", source, (movie_id,), str(tmdb_id)))
                else:
                    found[tmdb_id] = source
                link = links_by_movie.get(movie_id)
                if link is None or link.tmdb_id != tmdb_id:
                    bad.add(tmdb_id)
                    issues.append(MappingIssue("tmdb_link_conflict", source, (movie_id,), str(tmdb_id)))
                    continue
                if provider_id != tmdb_id:
                    bad.add(tmdb_id)
                    issues.append(MappingIssue("tmdb_provider_id_conflict", source, (movie_id,), str(tmdb_id)))
                if raw_imdb is not None and (link.imdb_id is None or raw_imdb != int(link.imdb_id)):
                    bad.add(tmdb_id)
                    issues.append(MappingIssue("tmdb_envelope_imdb_conflict", source, (movie_id,), str(tmdb_id)))
                if provider_imdb is not None and (link.imdb_id is None or provider_imdb != normalize_imdb_id(link.imdb_id)):
                    bad.add(tmdb_id)
                    issues.append(MappingIssue("tmdb_provider_imdb_conflict", source, (movie_id,), str(tmdb_id)))
    except OSError:
        raise DataValidationError("source_unavailable", source, "file") from None
    except UnicodeError:
        raise DataValidationError("encoding", source, "record") from None
    return found, duplicates | bad, issues


def build_movie_id_mapping(movielens_root: str | Path = DEFAULT_ROOT,
                           imdb_path: str | Path = DEFAULT_IMDB,
                           tmdb_path: str | Path = DEFAULT_TMDB) -> MovieIdMapping:
    """Validate all movie/link IDs, then stream external keys without loading payloads.

    Ambiguous external IDs and conflicting metadata are retained as issues, but
    their metadata sources are withheld from resolved records. Missing IDs and
    metadata remain explicit. Ratings/tags/user IDs are never opened or joined.
    """
    data = MovieLens(movielens_root)
    imdb_path, tmdb_path = Path(imdb_path).resolve(), Path(tmdb_path).resolve()
    paths = [data.root / "movies.csv", data.root / "links.csv", imdb_path, tmdb_path]
    before = {str(path): _fingerprint(path) for path in paths}
    movie_sources = {movie.movie_id: movie.source for movie in data.movies()}
    if not movie_sources:
        raise DataValidationError("empty_table", SourceRow(str(paths[0]), 1, 1, 1), "record")
    links = {link.movie_id: link for link in data.links(movie_ids=movie_sources)}
    if movie_sources.keys() != links.keys():
        raise DataValidationError("missing_movie_link", SourceRow(str(paths[1]), 1, 1, 1), "movieId")

    imdb_owners: dict[str, list[int]] = defaultdict(list)
    tmdb_owners: dict[int, list[int]] = defaultdict(list)
    for link in links.values():
        if link.imdb_id is not None:
            imdb_owners[normalize_imdb_id(link.imdb_id)].append(link.movie_id)
        if link.tmdb_id is not None:
            tmdb_owners[link.tmdb_id].append(link.movie_id)
    imdb_conflicts = {key for key, owners in imdb_owners.items() if len(owners) > 1}
    tmdb_conflicts = {key for key, owners in tmdb_owners.items() if len(owners) > 1}
    issues = [MappingIssue("imdb_id_collision", links[min(imdb_owners[key])].source,
                           tuple(sorted(imdb_owners[key])), key) for key in sorted(imdb_conflicts)]
    issues += [MappingIssue("tmdb_id_collision", links[min(tmdb_owners[key])].source,
                            tuple(sorted(tmdb_owners[key])), str(key)) for key in sorted(tmdb_conflicts)]

    imdb_found, imdb_duplicates = _imdb_rows(imdb_path, set(imdb_owners))
    tmdb_found, tmdb_bad, tmdb_issues = _tmdb_rows(tmdb_path, links, set(tmdb_owners))
    issues.extend(tmdb_issues)
    for key in sorted(imdb_duplicates):
        issues.append(MappingIssue("duplicate_imdb_metadata", imdb_found[key],
                                   tuple(sorted(imdb_owners[key])), key))

    records = {}
    for movie_id, link in links.items():
        tconst = normalize_imdb_id(link.imdb_id)
        imdb_conflict = tconst in imdb_conflicts or tconst in imdb_duplicates
        tmdb_conflict = link.tmdb_id in tmdb_conflicts or link.tmdb_id in tmdb_bad
        records[movie_id] = MovieIdRecord(
            movie_id, link.imdb_id, tconst, link.tmdb_id,
            movie_sources[movie_id], link.source,
            None if imdb_conflict else imdb_found.get(tconst),
            None if tmdb_conflict else tmdb_found.get(link.tmdb_id),
            imdb_conflict, tmdb_conflict,
        )
    unmatched_imdb = tuple(sorted(set(imdb_owners) - imdb_found.keys()))
    unmatched_tmdb = tuple(sorted(set(tmdb_owners) - tmdb_found.keys()))
    count = len(records)
    imdb_ids = sum(row.imdb_id is not None for row in records.values())
    tmdb_ids = sum(row.tmdb_id is not None for row in records.values())
    imdb_matched = sum(row.imdb_metadata_source is not None for row in records.values())
    tmdb_matched = sum(row.tmdb_metadata_source is not None for row in records.values())
    stats: dict[str, int | float] = {
        "movies": count, "links": len(links),
        "imdb_ids_present": imdb_ids, "tmdb_ids_present": tmdb_ids,
        "missing_imdb_ids": count - imdb_ids, "missing_tmdb_ids": count - tmdb_ids,
        "imdb_id_coverage": imdb_ids / count, "tmdb_id_coverage": tmdb_ids / count,
        "imdb_metadata_matched": imdb_matched, "tmdb_metadata_matched": tmdb_matched,
        "imdb_metadata_coverage": imdb_matched / count,
        "tmdb_metadata_coverage": tmdb_matched / count,
        "missing_imdb_metadata": imdb_ids - imdb_matched,
        "missing_tmdb_metadata": tmdb_ids - tmdb_matched,
        "unmatched_imdb_ids": len(unmatched_imdb), "unmatched_tmdb_ids": len(unmatched_tmdb),
        "imdb_collision_ids": len(imdb_conflicts), "tmdb_collision_ids": len(tmdb_conflicts),
        "duplicate_imdb_metadata_ids": len(imdb_duplicates),
        "conflicting_tmdb_metadata_ids": len(tmdb_bad),
    }
    after = {str(path): _fingerprint(path) for path in paths}
    if before != after:
        raise DataValidationError("source_changed", SourceRow(str(data.root), 0, 0, 0), "file")
    return MovieIdMapping(MappingProxyType(records), MappingProxyType(stats), tuple(issues),
                          unmatched_imdb, unmatched_tmdb,
                          MappingProxyType({key: MappingProxyType(value) for key, value in after.items()}))
