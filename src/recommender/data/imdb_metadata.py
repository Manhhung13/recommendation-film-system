"""DATA-005: read-only, target-filtered IMDb metadata enrichment.

Only links.csv IMDb IDs from a DATA-002 mapping are joined. The four local
TSV.GZ files are streamed, fingerprinted before and after, and never changed.
SourceUseEvidence is an audit assertion; callers must establish the facts.
"""
from __future__ import annotations

from dataclasses import dataclass
import gzip
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from .cleaning import RULES_VERSION, feature_eligibility
from .id_mapping import DEFAULT_IMDB, MovieIdMapping, _fingerprint
from .movielens import DataValidationError, SourceRow

TABLES = ("title.basics.tsv.gz", "title.crew.tsv.gz",
          "title.principals.tsv.gz", "name.basics.tsv.gz")
PROTECTED_IMDB_ROOT = (Path(__file__).resolve().parents[3] /
                       DEFAULT_IMDB.parent).resolve()
TCONST = re.compile(r"tt[0-9]+\Z", re.ASCII)
NCONST = re.compile(r"nm[0-9]+\Z", re.ASCII)
YEAR = re.compile(r"[0-9]{4}\Z", re.ASCII)
TEMPORAL_WARNING = (
    "IMDb daily export timestamps do not establish availability at MovieLens "
    "interaction times; exclude these fields from temporal features until review."
)


@dataclass(frozen=True, slots=True)
class ImdbSourceUseEvidence:
    source_version: str
    origin_evidence: str
    permitted_use_evidence: str
    expected_sha256: Mapping[str, str]
    synthetic_fixture: bool = False


@dataclass(frozen=True, slots=True)
class ImdbPerson:
    nconst: str
    name: str | None
    name_source: SourceRow | None
    ordering: int | None = None
    category: str | None = None


@dataclass(frozen=True, slots=True)
class ImdbMovie:
    movie_id: int
    imdb_id: str | None
    imdb_tconst: str | None
    runtime_minutes: int | None
    release_year: int | None
    genres: tuple[str, ...] | None
    directors: tuple[ImdbPerson, ...] | None
    writers: tuple[ImdbPerson, ...] | None
    actors: tuple[ImdbPerson, ...] | None
    source_rows: Mapping[str, SourceRow]
    imdb_allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImdbEnrichment:
    records: Mapping[int, ImdbMovie]
    stats: Mapping[str, int | float]
    issues: tuple[tuple[str, SourceRow, int], ...]
    sources: Mapping[str, Mapping[str, int | str]]
    source_use: ImdbSourceUseEvidence
    rules_version: str = RULES_VERSION
    temporal_warning: str = TEMPORAL_WARNING

    def __getitem__(self, movie_id: int) -> ImdbMovie:
        return self.records[movie_id]


def _target_rows(path: Path, required: tuple[str, ...], targets: set[str],
                 key_field: str, scanned: list[int]):
    """Stream only requested IDs; validate schema and each selected row."""
    header_source = SourceRow(str(path), 1, 1, 1)
    source = header_source
    try:
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            header = handle.readline().rstrip("\r\n").split("\t")
            if (not header or len(set(header)) != len(header)
                    or any(field not in header for field in required)):
                raise DataValidationError("schema", header_source, "header")
            columns = {name: header.index(name) for name in required}
            key_position = columns[key_field]
            for number, line in enumerate(handle, 2):
                scanned[0] += 1
                if key_position == 0 and line.partition("\t")[0] not in targets:
                    continue
                cells = line.rstrip("\r\n").split("\t")
                if len(cells) != len(header):
                    source = SourceRow(str(path), number, number, number)
                    raise DataValidationError("row_width", source, "record")
                if cells[key_position] not in targets:
                    continue
                source = SourceRow(str(path), number, number, number)
                yield cells, columns, source
    except (OSError, EOFError):
        raise DataValidationError("source_unavailable", source, "file") from None
    except UnicodeError:
        raise DataValidationError("encoding", source, "record") from None


def _natural(value: str, source: SourceRow, field: str,
             *, year: bool = False) -> int | None:
    if value == r"\N":
        return None
    if year:
        if not YEAR.fullmatch(value):
            raise DataValidationError("invalid_year", source, field)
    elif not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise DataValidationError("invalid_number", source, field)
    return int(value)


def _genres(value: str, source: SourceRow) -> tuple[str, ...] | None:
    if value == r"\N":
        return None
    parts = tuple(value.split(","))
    if not parts or any(not part or part.strip() != part for part in parts):
        raise DataValidationError("invalid_genres", source, "genres")
    if len(set(parts)) != len(parts):
        raise DataValidationError("duplicate_id", source, "genres")
    return parts


def _person_ids(value: str, source: SourceRow, field: str) -> tuple[str, ...] | None:
    if value == r"\N":
        return None
    values = tuple(value.split(","))
    if not values or any(not NCONST.fullmatch(item) for item in values):
        raise DataValidationError("invalid_id", source, field)
    if len(set(values)) != len(values):
        raise DataValidationError("duplicate_id", source, field)
    return values


def _name(value: str) -> str | None:
    return None if value == r"\N" else value.strip() or None


def load_imdb_metadata(mapping: MovieIdMapping, imdb_dir: str | Path, *,
                       source_use: ImdbSourceUseEvidence | None = None) -> ImdbEnrichment:
    """Enrich all MovieLens movie IDs while masking ambiguous IMDb features."""
    root = Path(imdb_dir).resolve()
    if not isinstance(source_use, ImdbSourceUseEvidence) or not all(
        isinstance(value, str) and value.strip()
        for value in (source_use.source_version, source_use.origin_evidence,
                      source_use.permitted_use_evidence)
    ):
        raise PermissionError("D-08 IMDb origin and permitted-use evidence required")
    if root.is_relative_to(PROTECTED_IMDB_ROOT) and source_use.synthetic_fixture:
        raise PermissionError("synthetic evidence cannot authorize local IMDb raw data")
    if (not isinstance(source_use.expected_sha256, Mapping)
            or set(source_use.expected_sha256) != set(TABLES) or any(
                not isinstance(value, str) or len(value) != 64 or
                any(char not in "0123456789abcdef" for char in value)
                for value in source_use.expected_sha256.values()
            )):
        raise ValueError("exact SHA-256 for all four IMDb TSV.GZ files is required")
    paths = {name: root / name for name in TABLES}
    before = {name: _fingerprint(path) for name, path in paths.items()}
    for name, info in before.items():
        if info["sha256"] != source_use.expected_sha256[name]:
            raise DataValidationError("source_hash_mismatch",
                                      SourceRow(str(paths[name]), 0, 0, 0), "file")
    basics_path = str(paths[TABLES[0]])
    if (basics_path not in mapping.sources or
            mapping.sources[basics_path]["sha256"] != before[TABLES[0]]["sha256"]):
        raise ValueError("movie ID mapping is not bound to this IMDb snapshot")

    owners = {record.imdb_tconst: movie_id for movie_id, record in mapping.records.items()
              if record.imdb_tconst is not None and not record.imdb_conflict
              and record.imdb_metadata_source is not None}
    targets = set(owners)
    scans = {name: [0] for name in TABLES}
    basics: dict[int, tuple[int | None, int | None, tuple[str, ...] | None, SourceRow]] = {}
    crew: dict[int, tuple[tuple[str, ...] | None, tuple[str, ...] | None, SourceRow]] = {}
    actors: dict[int, list[tuple[str, int, str]]] = {}
    principal_rows: dict[int, SourceRow] = {}
    person_ids: set[str] = set()
    ambiguous: set[int] = set()
    issues: list[tuple[str, SourceRow, int]] = [
        (issue.code, issue.source, movie_id)
        for issue in mapping.issues
        if issue.code.startswith("imdb") or issue.code == "duplicate_imdb_metadata"
        for movie_id in issue.movie_ids
    ]

    for cells, columns, source in _target_rows(
            paths[TABLES[0]], ("tconst", "startYear", "runtimeMinutes", "genres"),
            targets, "tconst", scans[TABLES[0]]):
        movie_id = owners[cells[columns["tconst"]]]
        if movie_id in basics:
            ambiguous.add(movie_id)
            issues.append(("duplicate_imdb_basics", source, movie_id))
            continue
        try:
            year = _natural(cells[columns["startYear"]], source, "startYear", year=True)
            runtime = _natural(cells[columns["runtimeMinutes"]], source, "runtimeMinutes")
            genres = _genres(cells[columns["genres"]], source)
        except DataValidationError as error:
            if error.code != "duplicate_id":
                raise
            ambiguous.add(movie_id)
            issues.append(("duplicate_imdb_genre", source, movie_id))
            continue
        basics[movie_id] = (runtime, year, genres, source)

    for cells, columns, source in _target_rows(
            paths[TABLES[1]], ("tconst", "directors", "writers"),
            targets, "tconst", scans[TABLES[1]]):
        movie_id = owners[cells[columns["tconst"]]]
        if movie_id in crew:
            ambiguous.add(movie_id)
            issues.append(("duplicate_imdb_crew", source, movie_id))
            continue
        try:
            directors = _person_ids(cells[columns["directors"]], source, "directors")
            writers = _person_ids(cells[columns["writers"]], source, "writers")
        except DataValidationError as error:
            if error.code != "duplicate_id":
                raise
            ambiguous.add(movie_id)
            issues.append(("duplicate_imdb_person_id", source, movie_id))
            continue
        crew[movie_id] = (directors, writers, source)
        person_ids.update(directors or ())
        person_ids.update(writers or ())

    seen_order: dict[int, set[int]] = {}
    for cells, columns, source in _target_rows(
            paths[TABLES[2]], ("tconst", "ordering", "nconst", "category"),
            targets, "tconst", scans[TABLES[2]]):
        movie_id = owners[cells[columns["tconst"]]]
        order = _natural(cells[columns["ordering"]], source, "ordering")
        nconst = cells[columns["nconst"]]
        if order is None or not NCONST.fullmatch(nconst):
            raise DataValidationError("invalid_id", source, "principal")
        orders = seen_order.setdefault(movie_id, set())
        if order in orders:
            ambiguous.add(movie_id)
            issues.append(("duplicate_imdb_principal", source, movie_id))
            continue
        orders.add(order)
        if cells[columns["category"]] in ("actor", "actress"):
            actors.setdefault(movie_id, []).append(
                (nconst, order, cells[columns["category"]]))
            principal_rows.setdefault(movie_id, source)
            person_ids.add(nconst)

    names: dict[str, tuple[str | None, SourceRow]] = {}
    duplicate_names: set[str] = set()
    for cells, columns, source in _target_rows(
            paths[TABLES[3]], ("nconst", "primaryName"),
            person_ids, "nconst", scans[TABLES[3]]):
        nconst = cells[columns["nconst"]]
        if nconst in names:
            duplicate_names.add(nconst)
            continue
        names[nconst] = (_name(cells[columns["primaryName"]]), source)

    def people(ids: tuple[str, ...] | None) -> tuple[ImdbPerson, ...] | None:
        if ids is None:
            return None
        return tuple(ImdbPerson(nconst, names[nconst][0] if nconst in names else None,
                                names[nconst][1] if nconst in names else None)
                     for nconst in ids)

    records = {}
    for movie_id, record in mapping.records.items():
        base = feature_eligibility(record)
        reasons = list(base.reasons)
        cast_ids = actors.get(movie_id, [])
        crew_ids = crew.get(movie_id)
        referenced = ({nconst for nconst, _, _ in cast_ids}
                      | set(crew_ids[0] or ()) | set(crew_ids[1] or ())
                      if crew_ids else {nconst for nconst, _, _ in cast_ids})
        if referenced & duplicate_names:
            ambiguous.add(movie_id)
            issues.append(("duplicate_imdb_name", basics.get(movie_id, (None, None, None,
                           record.movie_source))[3], movie_id))
        if movie_id in ambiguous:
            reasons.append("imdb_mapping_ambiguous")
        allowed = base.imdb_allowed and movie_id not in ambiguous and movie_id in basics
        if allowed:
            if crew_ids is None:
                reasons.append("imdb_crew_missing")
            if not cast_ids:
                reasons.append("imdb_cast_missing")
            if any(nconst not in names or names[nconst][0] is None for nconst in referenced):
                reasons.append("imdb_person_name_missing")
        fields = basics.get(movie_id) if allowed else None
        rows = {}
        if fields:
            rows[TABLES[0]] = fields[3]
        if allowed and crew_ids:
            rows[TABLES[1]] = crew_ids[2]
        if allowed and cast_ids:
            rows[TABLES[2]] = principal_rows[movie_id]
        records[movie_id] = ImdbMovie(
            movie_id, record.imdb_id, record.imdb_tconst,
            fields[0] if fields else None, fields[1] if fields else None,
            fields[2] if fields else None,
            people(crew_ids[0]) if allowed and crew_ids else None,
            people(crew_ids[1]) if allowed and crew_ids else None,
            tuple(ImdbPerson(nconst, names[nconst][0] if nconst in names else None,
                             names[nconst][1] if nconst in names else None,
                             order, category)
                  for nconst, order, category in sorted(cast_ids, key=lambda item: item[1]))
            if allowed and cast_ids else None,
            MappingProxyType(rows), allowed, tuple(dict.fromkeys(reasons)),
        )

    after = {name: _fingerprint(path) for name, path in paths.items()}
    if before != after:
        raise DataValidationError("source_changed", SourceRow(str(root), 0, 0, 0), "file")
    total = len(records)
    stats: dict[str, int | float] = {
        "movies": total,
        "imdb_ids_present": sum(row.imdb_id is not None for row in records.values()),
        "imdb_allowed": sum(row.imdb_allowed for row in records.values()),
        "imdb_quarantined": sum("imdb_mapping_ambiguous" in row.reasons for row in records.values()),
        "runtime_movies": sum(row.runtime_minutes is not None for row in records.values()),
        "year_movies": sum(row.release_year is not None for row in records.values()),
        "genres_movies": sum(row.genres is not None for row in records.values()),
        "director_movies": sum(row.directors is not None for row in records.values()),
        "writer_movies": sum(row.writers is not None for row in records.values()),
        "actor_movies": sum(row.actors is not None for row in records.values()),
        "missing_cast_movies": sum("imdb_cast_missing" in row.reasons for row in records.values()),
    }
    for name in TABLES:
        stats[name.removesuffix(".tsv.gz").replace(".", "_") + "_rows"] = scans[name][0]
    stats["imdb_coverage"] = stats["imdb_allowed"] / total if total else 0.0
    return ImdbEnrichment(MappingProxyType(records), MappingProxyType(stats),
                          tuple(issues), MappingProxyType({str(paths[name]): MappingProxyType(info)
                                                          for name, info in after.items()}),
                          source_use)
