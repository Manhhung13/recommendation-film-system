"""DATA-POLICY-001: non-destructive metadata quarantine and coverage audit."""
from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
import json
from math import ceil
from pathlib import Path

from .id_mapping import MovieIdMapping, MovieIdRecord, _fingerprint, build_movie_id_mapping
from .movielens import DataValidationError, MovieLens, Rating, SourceRow, source_snapshot

RULES_VERSION = "movie-metadata-quarantine-v1"


@dataclass(frozen=True, slots=True)
class FeatureEligibility:
    movie_id: int
    imdb_allowed: bool
    tmdb_allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProvenInvalidRow:
    """A documented proposal; never deletes or silently filters a raw row."""
    source: SourceRow
    source_sha256: str
    validation_code: str
    justification: str


def document_invalid_row(error: DataValidationError, *, source_sha256: str,
                         justification: str) -> ProvenInvalidRow:
    """Require a concrete validation failure and version-bound rationale."""
    if not isinstance(error, DataValidationError):
        raise TypeError("a DataValidationError is required")
    if (len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256)
            or not justification.strip()):
        raise ValueError("source SHA-256 and nonblank justification are required")
    return ProvenInvalidRow(error.source, source_sha256, error.code, justification.strip())


def feature_eligibility(record: MovieIdRecord) -> FeatureEligibility:
    """Withhold only the affected external feature; preserve the movie ID."""
    reasons = []
    for name in ("imdb", "tmdb"):
        if getattr(record, f"{name}_conflict"):
            reasons.append(f"{name}_mapping_ambiguous")
        elif getattr(record, f"{name}_id") is None:
            reasons.append(f"{name}_id_missing")
        elif getattr(record, f"{name}_metadata_source") is None:
            reasons.append(f"{name}_metadata_missing")
    return FeatureEligibility(record.movie_id, record.imdb_metadata_source is not None,
                              record.tmdb_metadata_source is not None, tuple(reasons))


def audit_cleaning(mapping: MovieIdMapping, ratings: Iterable[Rating]) -> dict:
    """Aggregate item, interaction and user impact using O(movies + users) memory.

    This consumes each validated rating once and never stores rating rows, user
    histories or user-level output. Popularity decile ties use movieId order.
    """
    if not mapping.records:
        raise ValueError("empty movie mapping")
    masks = {movie_id: feature_eligibility(row) for movie_id, row in mapping.records.items()}
    quarantined = {movie_id for movie_id, row in mapping.records.items()
                   if row.imdb_conflict or row.tmdb_conflict}
    imdb_ready = {movie_id for movie_id, mask in masks.items() if mask.imdb_allowed}
    tmdb_ready = {movie_id for movie_id, mask in masks.items() if mask.tmdb_allowed}
    both_ready = imdb_ready & tmdb_ready
    counts = dict.fromkeys(mapping.records, 0)
    all_users: set[int] = set()
    affected_users: set[int] = set()
    both_users: set[int] = set()
    imdb_users: set[int] = set()
    tmdb_users: set[int] = set()
    total = affected_ratings = both_ratings = imdb_ratings = tmdb_ratings = 0
    for rating in ratings:
        if rating.movie_id not in counts:
            raise DataValidationError("unknown_movieId", rating.source, "movieId")
        total += 1
        counts[rating.movie_id] += 1
        all_users.add(rating.user_id)
        if rating.movie_id in quarantined:
            affected_ratings += 1
            affected_users.add(rating.user_id)
        if rating.movie_id in imdb_ready:
            imdb_ratings += 1
            imdb_users.add(rating.user_id)
        if rating.movie_id in tmdb_ready:
            tmdb_ratings += 1
            tmdb_users.add(rating.user_id)
        if rating.movie_id in both_ready:
            both_ratings += 1
            both_users.add(rating.user_id)
    if not total:
        raise ValueError("empty ratings table")
    movie_count = len(counts)
    top_count = ceil(movie_count / 10)
    top = set(sorted(counts, key=lambda movie_id: (-counts[movie_id], movie_id))[:top_count])
    top_affected = len(top & quarantined)
    item_share = len(quarantined) / movie_count
    rating_share = affected_ratings / total
    return {
        "rules_version": RULES_VERSION,
        "status": "PASS",
        "raw_row_exclusions": 0,
        "quarantine": {
            "unique_movies": len(quarantined),
            "imdb_ambiguous_movies": sum(row.imdb_conflict for row in mapping.records.values()),
            "tmdb_ambiguous_movies": sum(row.tmdb_conflict for row in mapping.records.values()),
            "ratings": affected_ratings,
            "unique_rating_users": len(affected_users),
            "movie_share": item_share,
            "rating_share": rating_share,
            "user_share": len(affected_users) / len(all_users),
        },
        "metadata_feature_coverage": {
            "imdb": {"movies": len(imdb_ready), "ratings": imdb_ratings,
                     "users_with_eligible_rating": len(imdb_users)},
            "tmdb": {"movies": len(tmdb_ready), "ratings": tmdb_ratings,
                     "users_with_eligible_rating": len(tmdb_users)},
            "both": {"movies": len(both_ready), "ratings": both_ratings,
                     "users_with_eligible_rating": len(both_users)},
            "denominators": {"movies": movie_count, "ratings": total, "users": len(all_users)},
        },
        "model_ready_before": {"movies": movie_count, "ratings": total,
                               "users": len(all_users)},
        "model_ready_after": {
            "collaborative": {"movies": movie_count, "ratings": total,
                              "users": len(all_users)},
            "hybrid_candidates": {"movies": movie_count, "ratings": total,
                                  "users": len(all_users)},
            "both_external_metadata": {"movies": len(both_ready), "ratings": both_ratings,
                                       "users_with_eligible_rating": len(both_users)},
        },
        "popularity_bias": {
            "top_decile_definition": "ceil(10% of all movies), ratings descending, movieId tie break",
            "top_decile_movies": top_count,
            "top_decile_quarantined_movies": top_affected,
            "top_decile_quarantine_share": top_affected / top_count,
            "overall_quarantine_movie_share": item_share,
            "rating_to_movie_share_ratio": rating_share / item_share if item_share else None,
        },
    }


def audit_local_cleaning(movielens_root=None, imdb_path=None, tmdb_path=None) -> dict:
    """Read-only local audit with pre/post MovieLens and external source hashes."""
    data = MovieLens(movielens_root) if movielens_root is not None else MovieLens()
    before = source_snapshot(data.root)
    arguments = {"movielens_root": data.root}
    if imdb_path is not None:
        arguments["imdb_path"] = imdb_path
    if tmdb_path is not None:
        arguments["tmdb_path"] = tmdb_path
    mapping = build_movie_id_mapping(**arguments)
    report = audit_cleaning(mapping, data.ratings(movie_ids=mapping.records))
    after = source_snapshot(data.root)
    if before != after:
        raise DataValidationError("source_changed", SourceRow(str(data.root), 0, 0, 0), "file")
    for path, original in mapping.sources.items():
        if _fingerprint(Path(path)) != original:
            raise DataValidationError("source_changed", SourceRow(path, 0, 0, 0), "file")
    report["sources"] = {"movielens": after, "mapping": {p: dict(v) for p, v in mapping.sources.items()}}
    report["mapping_issue_counts"] = {
        code: sum(issue.code == code for issue in mapping.issues)
        for code in sorted({issue.code for issue in mapping.issues})
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only MovieRec cleaning impact audit")
    parser.parse_args()
    report = audit_local_cleaning()
    destination = Path(".runtime/evidence/DATA-POLICY-001/impact.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PASS: {report['quarantine']['unique_movies']} quarantined movies; {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
