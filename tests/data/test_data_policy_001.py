"""Acceptance tests for the owner-approved non-destructive cleaning policy."""
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data import DataValidationError, MovieLens, Rating, SourceRow
from recommender.data.cleaning import (
    RULES_VERSION, audit_cleaning, audit_local_cleaning, document_invalid_row,
    feature_eligibility,
)
from recommender.data.id_mapping import MovieIdMapping, MovieIdRecord


def record(movie_id, *, imdb=True, tmdb=True, imdb_conflict=False, tmdb_conflict=False):
    source = SourceRow("fixture.csv", movie_id + 1, movie_id + 1, movie_id + 1)
    return MovieIdRecord(
        movie_id, str(movie_id) if imdb else None,
        f"tt{movie_id:07d}" if imdb else None, movie_id if tmdb else None,
        source, source,
        source if imdb and not imdb_conflict else None,
        source if tmdb and not tmdb_conflict else None,
        imdb_conflict, tmdb_conflict,
    )


@pytest.fixture
def synthetic():
    records = {
        1: record(1),
        2: record(2, tmdb_conflict=True),
        3: record(3, imdb=False, tmdb=False),
        4: record(4, imdb_conflict=True),
        5: record(5, tmdb=False),
    }
    mapping = MovieIdMapping(records, {}, (), (), (), {})
    source = SourceRow("ratings.csv", 2, 2, 2)
    stamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
    ratings = [Rating(user, movie, 4.0, stamp, source)
               for movie, users in {1: (1, 2, 3, 4, 5), 2: (1, 2, 3, 4),
                                    3: (1, 2), 4: (1,)}.items() for user in users]
    return mapping, ratings


@pytest.mark.parametrize("case", ["masks", "retain_movie_ids", "no_raw_exclusion",
                                  "missing_is_not_ambiguous", "separate_external_sides"])
def test_data_policy_001_quarantine(synthetic, case):
    mapping, ratings = synthetic
    report = audit_cleaning(mapping, ratings)
    if case == "masks":
        assert feature_eligibility(mapping[2]).reasons == ("tmdb_mapping_ambiguous",)
        assert feature_eligibility(mapping[4]).reasons == ("imdb_mapping_ambiguous",)
    elif case == "retain_movie_ids":
        assert report["model_ready_before"] == report["model_ready_after"]["collaborative"]
        assert report["model_ready_before"] == report["model_ready_after"]["hybrid_candidates"]
        assert report["model_ready_before"] == {"movies": 5, "ratings": 12, "users": 5}
    elif case == "no_raw_exclusion":
        assert report["raw_row_exclusions"] == 0
        assert report["rules_version"] == RULES_VERSION
    elif case == "missing_is_not_ambiguous":
        assert feature_eligibility(mapping[3]).reasons == ("imdb_id_missing", "tmdb_id_missing")
        assert report["quarantine"]["unique_movies"] == 2
    elif case == "separate_external_sides":
        assert feature_eligibility(mapping[2]).imdb_allowed
        assert not feature_eligibility(mapping[2]).tmdb_allowed
        assert not feature_eligibility(mapping[4]).imdb_allowed
        assert feature_eligibility(mapping[4]).tmdb_allowed


@pytest.mark.parametrize("case", ["unique_impact", "coverage", "popularity",
                                  "unknown_movie_rejected", "no_ratings_rejected"])
def test_data_policy_001_impact(synthetic, case):
    mapping, ratings = synthetic
    if case == "unknown_movie_rejected":
        bad = Rating(1, 99, 4.0, ratings[0].timestamp, ratings[0].source)
        with pytest.raises(DataValidationError) as error:
            audit_cleaning(mapping, [bad])
        assert error.value.code == "unknown_movieId"
        return
    if case == "no_ratings_rejected":
        with pytest.raises(ValueError, match="empty ratings"):
            audit_cleaning(mapping, [])
        return
    report = audit_cleaning(mapping, ratings)
    if case == "unique_impact":
        assert report["quarantine"]["unique_movies"] == 2
        assert report["quarantine"]["ratings"] == 5
        assert report["quarantine"]["unique_rating_users"] == 4
        assert report["quarantine"]["user_share"] == 4 / 5
    elif case == "coverage":
        assert report["metadata_feature_coverage"]["denominators"] == {
            "movies": 5, "ratings": 12, "users": 5}
        assert report["metadata_feature_coverage"]["both"] == {
            "movies": 1, "ratings": 5, "users_with_eligible_rating": 5}
        assert report["model_ready_after"]["both_external_metadata"] == {
            "movies": 1, "ratings": 5, "users_with_eligible_rating": 5}
    elif case == "popularity":
        bias = report["popularity_bias"]
        assert bias["top_decile_movies"] == 1
        assert bias["top_decile_quarantined_movies"] == 0
        assert bias["rating_to_movie_share_ratio"] == (5 / 12) / (2 / 5)


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def raw(tmp_path):
    ml = tmp_path / "ml"
    ml.mkdir()
    write_csv(ml / "movies.csv", ["movieId", "title", "genres"],
              [(1, "Same", "Drama"), (2, "Same", "Drama")])
    write_csv(ml / "links.csv", ["movieId", "imdbId", "tmdbId"],
              [(1, "0000001", 10), (2, "0000002", 20)])
    write_csv(ml / "ratings.csv", ["userId", "movieId", "rating", "timestamp"],
              [(1, 1, "4.0", 0), (2, 2, "5.0", 1)])
    write_csv(ml / "tags.csv", ["userId", "movieId", "tag", "timestamp"],
              [(1, 1, "ok", 0)])
    imdb = tmp_path / "title.basics.tsv.gz"
    with gzip.open(imdb, "wt", encoding="utf-8") as handle:
        handle.write("tconst\ttitleType\n" "tt0000001\tmovie\n" "tt0000002\tmovie\n")
    tmdb = tmp_path / "movie_details.jsonl"
    entries = [{"movieId": m, "tmdbId": t, "imdbId": m,
                "data": {"id": t, "imdb_id": f"tt{m:07d}"}}
               for m, t in ((1, 10), (2, 20))]
    tmdb.write_text("".join(json.dumps(row) + "\n" for row in entries), encoding="utf-8")
    return ml, imdb, tmdb


@pytest.mark.parametrize("case", ["source_preservation", "invalid_row_fails",
                                  "documented_exclusion", "undocumented_exclusion_rejected"])
def test_data_policy_001_evidence(raw, case):
    ml, imdb, tmdb = raw
    if case == "source_preservation":
        paths = [*(ml / name for name in ("movies.csv", "links.csv", "ratings.csv", "tags.csv")),
                 imdb, tmdb]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        report = audit_local_cleaning(ml, imdb, tmdb)
        assert report["status"] == "PASS"
        assert report["model_ready_before"] == {"movies": 2, "ratings": 2, "users": 2}
        assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == before
        assert len(report["sources"]["mapping"]) == 4
    elif case == "invalid_row_fails":
        write_csv(ml / "ratings.csv", ["userId", "movieId", "rating", "timestamp"],
                  [(1, 1, "bad", 0)])
        with pytest.raises(DataValidationError) as error:
            audit_local_cleaning(ml, imdb, tmdb)
        assert error.value.code == "invalid_rating"
    elif case in ("documented_exclusion", "undocumented_exclusion_rejected"):
        error = DataValidationError("invalid_rating", SourceRow("ratings.csv", 2, 2, 2), "rating")
        sha = "a" * 64
        if case == "documented_exclusion":
            decision = document_invalid_row(error, source_sha256=sha,
                                            justification="Observed malformed rating text")
            assert (decision.validation_code, decision.source.record_number,
                    decision.source_sha256) == ("invalid_rating", 2, sha)
        else:
            with pytest.raises(ValueError):
                document_invalid_row(error, source_sha256=sha, justification="  ")
            with pytest.raises(ValueError):
                document_invalid_row(error, source_sha256="bad", justification="invalid")
            with pytest.raises(TypeError):
                document_invalid_row(ValueError("not proof"), source_sha256=sha,
                                     justification="invalid")
