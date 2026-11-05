"""DATA-004: read-only TMDb metadata normalization behind a D-08 use gate.

The loader streams three existing JSONL files, retaining only normalized
MovieLens-linked fields. It never makes network requests or writes raw data.
SourceUseEvidence is an audit assertion, not proof of account ownership; callers
must obtain and record the underlying facts before supplying real-data evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from .cleaning import RULES_VERSION, feature_eligibility
from .id_mapping import DEFAULT_TMDB, MovieIdMapping, _fingerprint
from .movielens import DataValidationError, SourceRow

TABLES = ("movie_details.jsonl", "keywords.jsonl", "credits.jsonl")
PROTECTED_TMDB_ROOT = (Path(__file__).resolve().parents[3] /
                       DEFAULT_TMDB.parent).resolve()
TEMPORAL_WARNING = (
    "TMDb fetch times do not establish availability at MovieLens interaction times; "
    "exclude these fields from temporal features until a separate leakage review."
)


@dataclass(frozen=True, slots=True)
class SourceUseEvidence:
    source_version: str
    origin_evidence: str
    permitted_use_evidence: str
    expected_sha256: Mapping[str, str]
    synthetic_fixture: bool = False


@dataclass(frozen=True, slots=True)
class NamedFacet:
    source_id: int
    name: str | None


@dataclass(frozen=True, slots=True)
class PersonCredit:
    source_id: int
    name: str | None
    role: str | None
    order: int | None


@dataclass(frozen=True, slots=True)
class TmdbMovie:
    movie_id: int
    tmdb_id: int | None
    imdb_id: str | None
    overview: str | None
    genres: tuple[NamedFacet, ...] | None
    keywords: tuple[NamedFacet, ...] | None
    cast: tuple[PersonCredit, ...] | None
    crew: tuple[PersonCredit, ...] | None
    release_date: date | None
    source_rows: Mapping[str, SourceRow]
    fetched_at_utc: datetime | None
    tmdb_allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TmdbEnrichment:
    records: Mapping[int, TmdbMovie]
    stats: Mapping[str, int | float]
    issues: tuple[tuple[str, SourceRow, int], ...]
    sources: Mapping[str, Mapping[str, int | str]]
    source_use: SourceUseEvidence
    rules_version: str = RULES_VERSION
    temporal_warning: str = TEMPORAL_WARNING

    def __getitem__(self, movie_id: int) -> TmdbMovie:
        return self.records[movie_id]


def _positive(value: object, source: SourceRow, field: str) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise DataValidationError("invalid_id", source, field)
    return value


def _optional_text(value: object, source: SourceRow, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or "\0" in value:
        raise DataValidationError("invalid_text", source, field)
    return value.strip() or None


def _date(value: object, source: SourceRow) -> date | None:
    text = _optional_text(value, source, "release_date")
    if text is None:
        return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        raise DataValidationError("invalid_date", source, "release_date")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise DataValidationError("invalid_date", source, "release_date") from None


def _fetched(value: object, source: SourceRow) -> datetime | None:
    text = _optional_text(value, source, "fetched_at_utc")
    if text is None:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise DataValidationError("invalid_timestamp", source, "fetched_at_utc") from None
    if stamp.tzinfo is None or stamp.utcoffset() != timezone.utc.utcoffset(stamp):
        raise DataValidationError("invalid_timestamp", source, "fetched_at_utc")
    return stamp.astimezone(timezone.utc)


def _facets(value: object, source: SourceRow, field: str
            ) -> tuple[NamedFacet, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise DataValidationError("schema", source, field)
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise DataValidationError("schema", source, field)
        key = _positive(item.get("id"), source, field + ".id")
        name = _optional_text(item.get("name"), source, field + ".name")
        if key in seen:
            raise DataValidationError("duplicate_id", source, field + ".id")
        seen.add(key)
        result.append(NamedFacet(key, name))
    return tuple(result)


def _credits(value: object, source: SourceRow, field: str
             ) -> tuple[PersonCredit, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise DataValidationError("schema", source, field)
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise DataValidationError("schema", source, field)
        key = _positive(item.get("id"), source, field + ".id")
        name = _optional_text(item.get("name"), source, field + ".name")
        role_field = "character" if field == "cast" else "job"
        role = _optional_text(item.get(role_field), source, field + "." + role_field)
        order = item.get("order") if field == "cast" else None
        if order is not None and (type(order) is not int or order < 0):
            raise DataValidationError("invalid_order", source, field + ".order")
        result.append(PersonCredit(key, name, role, order))
    return tuple(result)


def _rows(path: Path):
    source = SourceRow(str(path), 0, 0, 0)
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for number, line in enumerate(handle, 1):
                source = SourceRow(str(path), number, number, number)
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    raise DataValidationError("json_syntax", source, "record") from None
                if not isinstance(row, dict) or not isinstance(row.get("data"), dict):
                    raise DataValidationError("schema", source, "data")
                yield row, source
    except OSError:
        raise DataValidationError("source_unavailable", source, "file") from None
    except UnicodeError:
        raise DataValidationError("encoding", source, "record") from None


def _envelope(row: dict, source: SourceRow, table: str
              ) -> tuple[int, int, int | None, datetime | None, bool]:
    movie_id = _positive(row.get("movieId"), source, "movieId")
    tmdb_id = _positive(row.get("tmdbId"), source, "tmdbId")
    imdb_id = row.get("imdbId")
    if imdb_id is not None:
        imdb_id = _positive(imdb_id, source, "imdbId")
    provider_id = row["data"].get("id")
    provider_conflict = (provider_id is not None and
                         _positive(provider_id, source, "data.id") != tmdb_id)
    if table == "movie_details.jsonl" and provider_id is None:
        raise DataValidationError("schema", source, "data.id")
    return movie_id, tmdb_id, imdb_id, _fetched(row.get("fetched_at_utc"), source), provider_conflict


def _payload(table: str, data: dict, source: SourceRow) -> dict:
    if table == "movie_details.jsonl":
        return {"overview": _optional_text(data.get("overview"), source, "overview"),
                "genres": _facets(data.get("genres"), source, "genres"),
                "release_date": _date(data.get("release_date"), source)}
    if table == "keywords.jsonl":
        return {"keywords": _facets(data.get("keywords"), source, "keywords")}
    return {"cast": _credits(data.get("cast"), source, "cast"),
            "crew": _credits(data.get("crew"), source, "crew")}


def load_tmdb_metadata(mapping: MovieIdMapping, tmdb_dir: str | Path, *,
                       source_use: SourceUseEvidence | None = None) -> TmdbEnrichment:
    """Normalize existing files; mask ambiguous metadata, preserve all movie IDs.

    No source file is opened until explicit, version-bound source-use evidence is
    supplied. Synthetic evidence is refused for the repository's local raw root.
    """
    root = Path(tmdb_dir).resolve()
    if not isinstance(source_use, SourceUseEvidence) or not all(
        isinstance(value, str) and value.strip()
        for value in (source_use.source_version, source_use.origin_evidence,
                      source_use.permitted_use_evidence)
    ):
        raise PermissionError("D-08 origin and permitted-use evidence required")
    if root.is_relative_to(PROTECTED_TMDB_ROOT) and source_use.synthetic_fixture:
        raise PermissionError("synthetic evidence cannot authorize local TMDb raw data")
    if (not isinstance(source_use.expected_sha256, Mapping)
            or set(source_use.expected_sha256) != set(TABLES) or any(
                not isinstance(value, str) or len(value) != 64 or
                any(char not in "0123456789abcdef" for char in value)
                for value in source_use.expected_sha256.values()
            )):
        raise ValueError("exact SHA-256 for all three TMDb JSONL files is required")

    paths = {name: root / name for name in TABLES}
    before = {name: _fingerprint(path) for name, path in paths.items()}
    for name, fingerprint in before.items():
        if fingerprint["sha256"] != source_use.expected_sha256[name]:
            raise DataValidationError("source_hash_mismatch",
                                      SourceRow(str(paths[name]), 0, 0, 0), "file")
    details_path = str(paths["movie_details.jsonl"])
    if (details_path not in mapping.sources or
            mapping.sources[details_path]["sha256"] != before["movie_details.jsonl"]["sha256"]):
        raise ValueError("movie ID mapping is not bound to this TMDb snapshot")

    owners: dict[int, int] = {}
    for movie_id, record in mapping.records.items():
        if record.tmdb_id is not None and not record.tmdb_conflict:
            owners[record.tmdb_id] = movie_id
    found: dict[str, dict[int, tuple[dict, SourceRow, datetime | None]]] = {
        table: {} for table in TABLES
    }
    ambiguous: set[int] = set()
    issues: list[tuple[str, SourceRow, int]] = [
        (issue.code, issue.source, movie_id)
        for issue in mapping.issues
        if issue.code.startswith("tmdb") or issue.code == "duplicate_tmdb_metadata"
        for movie_id in issue.movie_ids
    ]
    scanned = dict.fromkeys(TABLES, 0)
    unmatched = dict.fromkeys(TABLES, 0)
    for table, path in paths.items():
        seen: set[int] = set()
        for envelope, source in _rows(path):
            scanned[table] += 1
            movie_id, tmdb_id, imdb_id, fetched, provider_conflict = _envelope(envelope, source, table)
            owner = owners.get(tmdb_id)
            if owner is None:
                unmatched[table] += 1
                continue
            if tmdb_id in seen:
                ambiguous.add(owner)
                issues.append(("duplicate_tmdb_metadata", source, owner))
                found[table].pop(owner, None)
                continue
            seen.add(tmdb_id)
            record = mapping[owner]
            if (provider_conflict or movie_id != owner or (imdb_id is not None and
                                     (record.imdb_id is None or imdb_id != int(record.imdb_id)))):
                ambiguous.add(owner)
                issues.append(("tmdb_provider_id_conflict" if provider_conflict
                               else "tmdb_link_conflict", source, owner))
                continue
            try:
                payload = _payload(table, envelope["data"], source)
            except DataValidationError as error:
                if error.code != "duplicate_id":
                    raise
                ambiguous.add(owner)
                issues.append(("tmdb_duplicate_facet_id", source, owner))
                continue
            found[table][owner] = (payload, source, fetched)

    records = {}
    for movie_id, record in mapping.records.items():
        base = feature_eligibility(record)
        reasons = list(base.reasons)
        if movie_id in ambiguous:
            reasons.append("tmdb_mapping_ambiguous")
        permitted = base.tmdb_allowed and movie_id not in ambiguous
        parts = {name: found[name].get(movie_id) if permitted else None for name in TABLES}
        if permitted:
            if parts["keywords.jsonl"] is None:
                reasons.append("tmdb_keywords_missing")
            if parts["credits.jsonl"] is None:
                reasons.append("tmdb_credits_missing")
            times = {part[2] for part in parts.values() if part is not None and part[2] is not None}
            if len(times) > 1:
                permitted = False
                reasons.append("tmdb_fetch_time_conflict")
                issues.append(("tmdb_fetch_time_conflict", parts["movie_details.jsonl"][1], movie_id))
        if not permitted:
            parts = dict.fromkeys(TABLES)
        details = parts["movie_details.jsonl"]
        keywords = parts["keywords.jsonl"]
        credits = parts["credits.jsonl"]
        rows = {name: part[1] for name, part in parts.items() if part is not None}
        records[movie_id] = TmdbMovie(
            movie_id, record.tmdb_id, record.imdb_id,
            details[0]["overview"] if details else None,
            details[0]["genres"] if details else None,
            keywords[0]["keywords"] if keywords else None,
            credits[0]["cast"] if credits else None,
            credits[0]["crew"] if credits else None,
            details[0]["release_date"] if details else None,
            MappingProxyType(rows), details[2] if details else None,
            permitted, tuple(dict.fromkeys(reasons)),
        )
    after = {name: _fingerprint(path) for name, path in paths.items()}
    if before != after:
        raise DataValidationError("source_changed", SourceRow(str(root), 0, 0, 0), "file")
    total = len(records)
    stats = {"movies": total,
             "tmdb_ids_present": sum(row.tmdb_id is not None for row in records.values()),
             "tmdb_allowed": sum(row.tmdb_allowed for row in records.values()),
             "tmdb_quarantined": sum("tmdb_mapping_ambiguous" in row.reasons or
                                     "tmdb_fetch_time_conflict" in row.reasons
                                     for row in records.values()),
             "overview_movies": sum(row.overview is not None for row in records.values()),
             "genres_movies": sum(row.genres is not None for row in records.values()),
             "keywords_movies": sum(row.keywords is not None for row in records.values()),
             "cast_movies": sum(row.cast is not None for row in records.values()),
             "crew_movies": sum(row.crew is not None for row in records.values()),
             "release_date_movies": sum(row.release_date is not None for row in records.values())}
    for table in TABLES:
        label = table.removesuffix(".jsonl")
        stats[label + "_rows"] = scanned[table]
        stats[label + "_unmatched_rows"] = unmatched[table]
    stats["tmdb_coverage"] = stats["tmdb_allowed"] / total if total else 0.0
    return TmdbEnrichment(MappingProxyType(records), MappingProxyType(stats),
                          tuple(issues), MappingProxyType({str(paths[name]): MappingProxyType(value)
                                                          for name, value in after.items()}),
                          source_use)
