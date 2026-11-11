"""DATA-006: Versioned, read-only Movie Feature Store integration.

Join only by MovieLens movieId and links.csv identities. Keep MovieLens rows,
quarantine ambiguous external metadata, and record reproducible source fingerprints.
No raw data or external service is modified or fetched.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .cleaning import RULES_VERSION, feature_eligibility
from .id_mapping import (
    DEFAULT_IMDB,
    DEFAULT_TMDB,
    MovieIdMapping,
    build_movie_id_mapping,
)
from .imdb_metadata import ImdbSourceUseEvidence, load_imdb_metadata
from .movielens import DataValidationError, MovieLens, SourceRow, source_snapshot
from .tag_genome import GenomeMovie, load_tag_genome
from .tmdb_metadata import SourceUseEvidence, load_tmdb_metadata

SCHEMA_VERSION = "movie-feature-store-v1"


@dataclass(frozen=True, slots=True)
class MovieFeatureRecord:
    movie_id: int
    title: str
    genres: tuple[str, ...]
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tag_genome: GenomeMovie | None = None
    overview: str | None = None
    keywords: tuple[str, ...] | None = None
    cast: tuple[str, ...] | None = None
    director: str | None = None
    runtime_minutes: int | None = None
    release_year: int | None = None
    source_provenance: Mapping[str, object] | None = None
    imdb_allowed: bool = True
    tmdb_allowed: bool = True
    quarantine_mask: tuple[str, ...] | None = None

    def validate(self) -> tuple[bool, list[str]]:
        return validate_feature_record(self)


def validate_feature_record(record: MovieFeatureRecord) -> tuple[bool, list[str]]:
    """Basic schema guard; source-level checks belong to DATA-QUALITY-001."""
    errors = []
    if type(record.movie_id) is not int or record.movie_id <= 0:
        errors.append("movie_id must be a positive integer")
    if not isinstance(record.title, str) or not record.title.strip():
        errors.append("title must be a non-empty string")
    if not isinstance(record.genres, tuple) or not all(
        isinstance(g, str) and g.strip() for g in record.genres
    ):
        errors.append("genres must be a tuple of non-empty strings")
    if not isinstance(record.source_provenance, Mapping) or not record.source_provenance:
        errors.append("source_provenance is required")
    return not errors, errors


def _names(items: object) -> tuple[str, ...] | None:
    """Convert TMDb NamedFacet/PersonCredit tuples to strings without fake values."""
    if items is None:
        return None
    return tuple(item.name for item in items if item.name)


def build_movie_feature_store(
    movielens_root: str | Path,
    imdb_dir: str | Path | None = None,
    tmdb_dir: str | Path | None = None,
    *,
    source_use_imdb: ImdbSourceUseEvidence | None = None,
    source_use_tmdb: SourceUseEvidence | None = None,
    tag_genome_path: str | Path | None = None,
) -> tuple[dict[int, MovieFeatureRecord], dict[str, object],
           tuple[tuple[str, SourceRow, int], ...]]:
    """Return (movie records, source provenance, issues), without altering raw data.

    IMDb and TMDb enrichment requires corresponding version-bound source-use
    evidence validated by the DATA-004/005 loaders. The mapping still validates
    the local external identity snapshots when enrichment is disabled.
    """
    ml_root = Path(movielens_root).resolve()
    imdb_path = Path(imdb_dir) / "title.basics.tsv.gz" if imdb_dir is not None else DEFAULT_IMDB
    tmdb_path = Path(tmdb_dir) / "movie_details.jsonl" if tmdb_dir is not None else DEFAULT_TMDB

    # Snapshot the four MovieLens raw tables (including ratings and tags).
    before = source_snapshot(ml_root)
    mapping: MovieIdMapping = build_movie_id_mapping(
        ml_root, imdb_path=imdb_path, tmdb_path=tmdb_path,
    )
    movies = {movie.movie_id: movie for movie in MovieLens(ml_root).movies()}
    if movies.keys() != mapping.records.keys():
        raise ValueError("Feature store/movie ID mapping mismatch")

    imdb = (load_imdb_metadata(mapping, imdb_dir, source_use=source_use_imdb)
            if imdb_dir is not None else None)
    tmdb = (load_tmdb_metadata(mapping, tmdb_dir, source_use=source_use_tmdb)
            if tmdb_dir is not None else None)
    genome = None
    if tag_genome_path is not None:
        genome_root = Path(tag_genome_path).resolve()
        if genome_root.is_file():
            genome_root = genome_root.parent
        if not genome_root.is_dir():
            raise FileNotFoundError(f"Missing Tag Genome directory: {genome_root}")
        genome = load_tag_genome(genome_root)
        if genome.movie_ids != movies.keys():
            raise ValueError("Tag Genome movie ID coverage does not match MovieLens")

    issues: list[tuple[str, SourceRow, int]] = [
        (issue.code, issue.source, movie_id)
        for issue in mapping.issues for movie_id in issue.movie_ids
    ]
    if imdb is not None:
        issues.extend(imdb.issues)
    if tmdb is not None:
        issues.extend(tmdb.issues)

    after = source_snapshot(ml_root)
    if before != after:
        raise DataValidationError(
            "source_changed", SourceRow(str(ml_root), 0, 0, 0), "file"
        )

    provenance: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "quarantine_policy_version": RULES_VERSION,
        "movielens_sources": after,
        "mapping_sources": {k: dict(v) for k, v in mapping.sources.items()},
        "imdb_sources": {k: dict(v) for k, v in imdb.sources.items()} if imdb else None,
        "tmdb_sources": {k: dict(v) for k, v in tmdb.sources.items()} if tmdb else None,
        "tag_genome_sources": {k: dict(v) for k, v in genome.sources.items()} if genome else None,
        "tag_genome_version": genome.source_version if genome else None,
    }

    records: dict[int, MovieFeatureRecord] = {}
    for movie_id, mapping_row in mapping.records.items():
        movie = movies[movie_id]
        eligibility = feature_eligibility(mapping_row)
        imdb_row = imdb.records.get(movie_id) if imdb is not None else None
        tmdb_row = tmdb.records.get(movie_id) if tmdb is not None else None

        # Availability and ambiguity are distinct: only ambiguity is quarantined.
        imdb_ambiguous = mapping_row.imdb_conflict or bool(
            imdb_row is not None and any(
                reason in {"imdb_mapping_ambiguous", "duplicate_imdb_name"}
                for reason in imdb_row.reasons
            )
        )
        tmdb_ambiguous = mapping_row.tmdb_conflict or bool(
            tmdb_row is not None and any(
                reason in {"tmdb_mapping_ambiguous", "tmdb_fetch_time_conflict"}
                for reason in tmdb_row.reasons
            )
        )
        imdb_ready = bool(
            eligibility.imdb_allowed and imdb_row is not None
            and imdb_row.imdb_allowed and not imdb_ambiguous
        )
        tmdb_ready = bool(
            eligibility.tmdb_allowed and tmdb_row is not None
            and tmdb_row.tmdb_allowed and not tmdb_ambiguous
        )
        masks = tuple(
            name for name, active in (
                ("imdb_quarantined", imdb_ambiguous),
                ("tmdb_quarantined", tmdb_ambiguous),
            ) if active
        )

        title = movie.title
        genres = movie.genres
        tmdb_id = None if tmdb_ambiguous else mapping_row.tmdb_id
        imdb_id = None if imdb_ambiguous else mapping_row.imdb_tconst
        overview = keywords = cast = director = runtime = year = None

        if tmdb_ready:
            overview = tmdb_row.overview
            keywords = _names(tmdb_row.keywords)
            cast = _names(tmdb_row.cast)
            directors = tuple(
                p.name for p in (tmdb_row.crew or ())
                if p.name and p.role and p.role.casefold() == "director"
            )
            director = directors[0] if directors else None
            year = tmdb_row.release_date.year if tmdb_row.release_date else None

        if imdb_ready:
            if imdb_row.genres:
                genres = imdb_row.genres
            if imdb_row.runtime_minutes is not None:
                runtime = imdb_row.runtime_minutes
            if imdb_row.release_year is not None:
                year = imdb_row.release_year
            if not director:
                names = _names(imdb_row.directors)
                director = names[0] if names else None
            if cast is None:
                cast = _names(imdb_row.actors)

        feature = MovieFeatureRecord(
            movie_id=movie_id,
            title=title,
            genres=genres,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            tag_genome=genome.movies.get(movie_id) if genome else None,
            overview=overview,
            keywords=keywords,
            cast=cast,
            director=director,
            runtime_minutes=runtime,
            release_year=year,
            source_provenance={
                "movie_id": movie_id,
                "schema_version": SCHEMA_VERSION,
                "sources": provenance,
                "movie_row": {
                    "file": movie.source.source_file,
                    "record": movie.source.record_number,
                    "line_start": movie.source.line_start,
                    "line_end": movie.source.line_end,
                },
                "link_row": {
                    "file": mapping_row.link_source.source_file,
                    "record": mapping_row.link_source.record_number,
                    "line_start": mapping_row.link_source.line_start,
                    "line_end": mapping_row.link_source.line_end,
                },
                "external_missing_or_ineligible": eligibility.reasons,
                "imdb_missing": not imdb_ready,
                "tmdb_missing": not tmdb_ready,
            },
            imdb_allowed=imdb_ready,
            tmdb_allowed=tmdb_ready,
            quarantine_mask=masks,
        )
        valid, errors = feature.validate()
        if not valid:
            raise ValueError(f"Invalid feature record for movieId={movie_id}: {errors}")
        records[movie_id] = feature

    return records, provenance, tuple(issues)
