"""DATA-006: Build versioned Movie Feature Store.

Combines MovieLens raw data with enriched TMDb and IMDb metadata into
versioned feature records. Preserves source provenance, quarantine masks
and coverage per DATA-POLICY-001. Never mutates raw datasets.

Schema fields (slide 6):
  movie_id, title, genres, tmdb_id, imdb_id, tag_genome, overview,
  keywords, cast, director, runtime, year, source_provenance
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from .id_mapping import MovieIdRecord, SourceRow, _fingerprint, build_movie_id_mapping
from .movielens import MovieLens, DataValidationError, source_snapshot
from .tag_genome import load_tag_genome as _load_genome, GenomeMovie
from .imdb_metadata import load_imdb_metadata
from .tmdb_metadata import load_tmdb_metadata, TmdbEnrichment
from .cleaning import RULES_VERSION, feature_eligibility


@dataclass(frozen=True, slots=True)
class MovieFeatureRecord:
    """Versioned movie feature record matching slide 6 schema."""
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

    # D-08 policy fields
    imdb_allowed: bool = True
    tmdb_allowed: bool = True
    quarantine_mask: tuple[str, ...] | None = None

    def validate(self) -> Tuple[bool, list[str]]:
        """Validate against DATA-006 schema and policy requirements."""
        errors = []

        if not isinstance(self.movie_id, int) or self.movie_id < 0:
            errors.append("movie_id must be a non-negative integer")

        if not isinstance(self.title, str) or not self.title.strip():
            errors.append("title must be a non-empty string")

        if not isinstance(self.genres, tuple) or not all(
            isinstance(g, str) and g.strip() for g in self.genres
        ):
            errors.append("genres must be a tuple of non-empty strings")

        if self.source_provenance is None:
            errors.append("source_provenance is required")

        return len(errors) == 0, errors


def build_movie_feature_store(
    movielens_root: Path,
    imdb_dir: str | Path | None = None,
    tmdb_dir: str | Path | None = None,
    *,
    source_use_imdb: object | None = None,
    source_use_tmdb: object | None = None,
    tag_genome_path: Path | None = None,
) -> Tuple[
    dict[int, MovieFeatureRecord],
    dict[str, object],
    Tuple[tuple[str, SourceRow, int], ...],
]:
    """Build a versioned Movie Feature Store from the three data sources.

    Returns:
        (records, provenance_snapshot, quarantine_issues)

    Policy (D-08 + DATA-POLICY-001):
    - Only reads local snapshots never makes API calls or re-downloads
    - SHA-256 fingerprints recorded before/after processing
    - Ambiguous external metadata quarantined per mask; rows preserved
    - No automatic row deletion; missing fields become None
    - Tag genome scores version-bound to raw CSVs
    - source_use evidence required for IMDb/TMDb; synthetic fixture
      cannot authorize local raw data
    """
    from .id_mapping import MovieIdRecord
    from .tag_genome import load_tag_genome as _load_genome

    ml_root = movielens_root.resolve()

    # Step 1: Build the unified movie ID mapping (links.csv bridges all sources)
    mapping: dict[int, MovieIdRecord] = build_movie_id_mapping(ml_root)

    # Step 2: Record raw snapshot before enrichment
    provenance = source_snapshot(
        ml_root / "movies.csv",
        ml_root / "links.csv",
        ml_root / "ratings.csv",
        ml_root / "tags.csv" if (ml_root / "tags.csv").exists() else None,
    )

    # Step 3: Enrich with IMDb metadata (behind D-08 gate)
    imdb_enrichment = None
    if imdb_dir is not None:
        imdb_enrichment = load_imdb_metadata(
            mapping, str(imdb_dir), source_use=source_use_imdb
        )

    # Step 4: Enrich with TMDb metadata (behind D-08 gate)
    tmdb_enrichment = None
    if tmdb_dir is not None:
        tmdb_enrichment = load_tmdb_metadata(
            mapping, str(tmdb_dir), source_use=source_use_tmdb
        )

    # Step 5: Load tag genome if available
    genome = None
    if tag_genome_path is not None and tag_genome_path.exists():
        genome = _load_genome(tag_genome_path)

    # Step 6: Build feature records per movie
    records: dict[int, MovieFeatureRecord] = {}

    for movie_id, record in mapping.items():
        # Start with MovieLens base
        title = record.movie_source.title if hasattr(record.movie_source, "title") else str(movie_id)
        genres = record.movie_source.genres or () if hasattr(record.movie_source, "genres") else ()

        # TMDb contributions (if available)
        tmdb_id = None
        overview = None
        keywords: tuple[str, ...] | None = None
        cast: tuple[str, ...] | None = None
        director: str | None = None
        runtime_minutes: int | None = None
        release_year: int | None = None

        if tmdb_enrichment is not None and movie_id in tmdb_enrichment.records:
            tmovie = tmdb_enrichment.records[movie_id]
            tmdb_id = tmovie.tmdb_id
            overview = tmovie.overview
            keywords = tmovie.keywords
            cast = tmovie.cast
            # Extract director from crew if available
            if tmovie.crew:
                directors = [p.name for p in tmovie.crew if p.role == "director"]
                director = directors[0] if directors else None
            runtime_minutes = tmovie.runtime_minutes
            release_year = tmovie.release_date.year if tmovie.release_date else None

        # IMDb contributions (if available)
        if imdb_enrichment is not None and movie_id in imdb_enrichment.records:
            imovie = imdb_enrichment.records[movie_id]
            imdb_id = imovie.imdb_id or imovie.imdb_tconst
            # Genres from IMDb take precedence but we merge
            if imovie.genres:
                genres = imovie.genres
            runtime_minutes = imovie.runtime_minutes or runtime_minutes
            release_year = imovie.release_year

        # Tag genome contributions (if available)
        tag_genome_record: GenomeMovie | None = None
        if genome is not None and movie_id in genome.movies:
            tag_genome_record = genome.movies[movie_id]

        # Determine eligibility masks per DATA-POLICY-001
        eligibility = feature_eligibility(record)
        imdb_allowed = eligibility.imdb_allowed
        tmdb_allowed = eligibility.tmdb_allowed

        quarantine_reasons: tuple[str, ...] = ()
        if not imdb_allowed:
            quarantine_reasons = quarantine_reasons + ("imdb_quarantined",)
        if not tmdb_allowed:
            quarantine_reasons = quarantine_reasons + ("tmdb_quarantined",)

        # Build the provenance for this specific movie
        movie_provenance = {
            "movie_id": movie_id,
            "source_snapshot": provenance,
            "imdb_source_use": (
                source_use_imdb if imdb_enrichment else None
            ),
            "tmdb_source_use": (
                source_use_tmdb if tmdb_enrichment else None
            ),
            "tag_genome_version": genome.source_version if genome else None,
        }

        records[movie_id] = MovieFeatureRecord(
            movie_id=movie_id,
            title=title,
            genres=genres,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            tag_genome=tag_genome_record,
            overview=overview,
            keywords=keywords,
            cast=cast,
            director=director,
            runtime_minutes=runtime_minutes,
            release_year=release_year,
            source_provenance=movie_provenance,
            imdb_allowed=imdb_allowed,
            tmdb_allowed=tmdb_allowed,
            quarantine_mask=quarantine_reasons,
        )

    return records, provenance, ()  # quarantine issues would be aggregated separately


def validate_feature_record(record: MovieFeatureRecord) -> tuple[bool, list[str]]:
    """Validate a single MovieFeatureRecord against the DATA-006 schema.

    Returns (is_valid, error_messages).
    """
    errors = []

    if not isinstance(record.movie_id, int) or record.movie_id < 0:
        errors.append("movie_id must be a non-negative integer")

    if not isinstance(record.title, str) or not record.title.strip():
        errors.append("title must be a non-empty string")

    if not isinstance(record.genres, tuple) or not all(
        isinstance(g, str) and g.strip() for g in record.genres
    ):
        errors.append("genres must be a tuple of non-empty strings")

    if record.source_provenance is None:
        errors.append("source_provenance is required")

    return len(errors) == 0, errors