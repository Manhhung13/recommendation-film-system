"""DATA-005 synthetic acceptance tests; no real IMDb records or network."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data import (
    DataValidationError, ImdbSourceUseEvidence, build_movie_id_mapping,
    load_imdb_metadata,
)
from recommender.data.id_mapping import DEFAULT_IMDB

TABLES = ("title.basics.tsv.gz", "title.crew.tsv.gz",
          "title.principals.tsv.gz", "name.basics.tsv.gz")
HEADERS = {
    TABLES[0]: ("tconst", "titleType", "primaryTitle", "originalTitle", "isAdult",
                "startYear", "endYear", "runtimeMinutes", "genres"),
    TABLES[1]: ("tconst", "directors", "writers"),
    TABLES[2]: ("tconst", "ordering", "nconst", "category", "job", "characters"),
    TABLES[3]: ("nconst", "primaryName", "birthYear", "deathYear",
                "primaryProfession", "knownForTitles"),
}


def csv_table(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def gz_table(path, rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
        writer.writerow(HEADERS[path.name])
        writer.writerows(rows)


@pytest.fixture
def synthetic(tmp_path):
    ml, imdb, tmdb = (tmp_path / name for name in ("ml", "imdb", "tmdb"))
    ml.mkdir()
    imdb.mkdir()
    tmdb.mkdir()
    csv_table(ml / "movies.csv", ("movieId", "title", "genres"),
              [(1, "MovieLens title", "Drama"), (2, "Second", "Comedy"),
               (3, "No IMDb ID", "Drama")])
    csv_table(ml / "links.csv", ("movieId", "imdbId", "tmdbId"),
              [(1, "0000001", "10"), (2, "0000002", "20"), (3, "", "")])
    csv_table(ml / "ratings.csv", ("userId", "movieId", "rating", "timestamp"),
              [(9, 1, 4, 100), (9, 2, 5, 200), (8, 3, 3, 300)])
    (tmdb / "movie_details.jsonl").write_text(
        "".join(json.dumps({"movieId": movie, "imdbId": movie, "tmdbId": provider,
                            "data": {"id": provider, "imdb_id": f"tt{movie:07d}"}}) + "\n"
                for movie, provider in ((1, 10), (2, 20))), encoding="utf-8")
    gz_table(imdb / TABLES[0], [
        ("tt0000001", "movie", "IMDb unrelated title", "Other", "0", "2001", r"\N", "120", "Drama,Thriller"),
        ("tt0000002", "movie", "Second", "Second", "0", r"\N", r"\N", r"\N", r"\N"),
    ])
    gz_table(imdb / TABLES[1], [
        ("tt0000001", "nm0000001", "nm0000002"),
        ("tt0000002", r"\N", r"\N"),
    ])
    gz_table(imdb / TABLES[2], [
        ("tt0000001", "1", "nm0000003", "actor", r"\N", r"\N"),
        ("tt0000001", "2", "nm0000001", "director", r"\N", r"\N"),
        ("tt0000002", "1", "nm0000002", "director", r"\N", r"\N"),
    ])
    gz_table(imdb / TABLES[3], [
        ("nm0000001", " Director ", r"\N", r"\N", r"\N", r"\N"),
        ("nm0000002", "Writer", r"\N", r"\N", r"\N", r"\N"),
        ("nm0000003", "Actor", r"\N", r"\N", r"\N", r"\N"),
    ])
    return ml, imdb, tmdb


def evidence(imdb):
    return ImdbSourceUseEvidence(
        source_version="synthetic-v1", origin_evidence="pytest fixture",
        permitted_use_evidence="synthetic unrestricted", synthetic_fixture=True,
        expected_sha256={name: hashlib.sha256((imdb / name).read_bytes()).hexdigest()
                         for name in TABLES},
    )


def mapping(synthetic):
    ml, imdb, tmdb = synthetic
    return build_movie_id_mapping(ml, imdb / TABLES[0], tmdb / "movie_details.jsonl")


def load(synthetic):
    return load_imdb_metadata(mapping(synthetic), synthetic[1],
                              source_use=evidence(synthetic[1]))


def test_data_005_ac_01(synthetic):
    ratings_before = (synthetic[0] / "ratings.csv").read_bytes()
    result = load(synthetic)
    one = result[1]
    assert set(result.records) == {1, 2, 3}
    assert one.imdb_allowed and one.imdb_id == "0000001" and one.imdb_tconst == "tt0000001"
    assert one.runtime_minutes == 120 and one.release_year == 2001
    assert one.genres == ("Drama", "Thriller")
    assert [(person.nconst, person.name) for person in one.directors] == [("nm0000001", "Director")]
    assert [(person.nconst, person.name) for person in one.writers] == [("nm0000002", "Writer")]
    assert [(person.nconst, person.name, person.ordering, person.category)
            for person in one.actors] == [("nm0000003", "Actor", 1, "actor")]
    assert one.actors[0].name_source.record_number == 4
    assert (synthetic[0] / "ratings.csv").read_bytes() == ratings_before


def test_data_005_ac_02(synthetic):
    result = load(synthetic)
    one = result[1]
    assert one.imdb_id == "0000001" and one.imdb_tconst == "tt0000001"
    assert one.source_rows[TABLES[0]].record_number == 2
    assert one.source_rows[TABLES[1]].record_number == 2
    assert one.source_rows[TABLES[2]].record_number == 2
    assert set(result.sources) == {str(synthetic[1] / name) for name in TABLES}
    assert all(result.sources[str(synthetic[1] / name)]["sha256"] == evidence(synthetic[1]).expected_sha256[name]
               for name in TABLES)
    assert result.source_use.source_version == "synthetic-v1"
    assert result.rules_version == "movie-metadata-quarantine-v1"
    assert "interaction times" in result.temporal_warning
    assert result.stats["movies"] == 3 and result.stats["imdb_allowed"] == 2
    assert result[3].imdb_id is None and result[3].runtime_minutes is None


def test_data_005_ac_03(synthetic):
    result = load(synthetic)
    two = result[2]
    assert two.imdb_allowed and two.runtime_minutes is None
    assert two.release_year is None and two.genres is None
    assert two.actors is None and "imdb_cast_missing" in two.reasons
    assert two.directors is None and two.writers is None
    assert result.stats["missing_cast_movies"] == 1


@pytest.mark.parametrize("case", [
    "duplicate_basics", "duplicate_crew", "duplicate_principal_order",
    "duplicate_name", "duplicate_genre", "duplicate_director",
    "missing_crew", "missing_actor_name", "invalid_year", "invalid_runtime",
    "invalid_principal_id",
])
def test_data_005_edge_cases(synthetic, case):
    imdb = synthetic[1]
    if case == "duplicate_basics":
        with gzip.open(imdb / TABLES[0], "at", encoding="utf-8") as handle:
            handle.write("tt0000001\tmovie\tDuplicate\tDuplicate\t0\t2001\t\\N\t120\tDrama\n")
    elif case == "duplicate_crew":
        gz_table(imdb / TABLES[1], [("tt0000001", "nm0000001", "nm0000002"),
                                    ("tt0000001", "nm0000001", "nm0000002")])
    elif case == "duplicate_principal_order":
        gz_table(imdb / TABLES[2], [("tt0000001", "1", "nm0000003", "actor", r"\N", r"\N"),
                                    ("tt0000001", "1", "nm0000002", "actress", r"\N", r"\N")])
    elif case == "duplicate_name":
        gz_table(imdb / TABLES[3], [("nm0000001", "One", r"\N", r"\N", r"\N", r"\N"),
                                    ("nm0000001", "Two", r"\N", r"\N", r"\N", r"\N")])
    elif case == "duplicate_genre":
        gz_table(imdb / TABLES[0], [("tt0000001", "movie", "One", "One", "0", "2001", r"\N", "120", "Drama,Drama"),
                                    ("tt0000002", "movie", "Two", "Two", "0", r"\N", r"\N", r"\N", r"\N")])
    elif case == "duplicate_director":
        gz_table(imdb / TABLES[1], [("tt0000001", "nm0000001,nm0000001", "nm0000002"),
                                    ("tt0000002", r"\N", r"\N")])
    elif case == "missing_crew":
        gz_table(imdb / TABLES[1], [("tt0000002", r"\N", r"\N")])
    elif case == "missing_actor_name":
        gz_table(imdb / TABLES[3], [("nm0000001", "Director", r"\N", r"\N", r"\N", r"\N"),
                                    ("nm0000002", "Writer", r"\N", r"\N", r"\N", r"\N")])
    elif case in ("invalid_year", "invalid_runtime"):
        year, runtime = ("20x1", "120") if case == "invalid_year" else ("2001", "zero")
        gz_table(imdb / TABLES[0], [("tt0000001", "movie", "One", "One", "0", year, r"\N", runtime, "Drama"),
                                    ("tt0000002", "movie", "Two", "Two", "0", r"\N", r"\N", r"\N", r"\N")])
    else:
        gz_table(imdb / TABLES[2], [("tt0000001", "1", "bad", "actor", r"\N", r"\N")])

    if case.startswith("invalid_"):
        with pytest.raises(DataValidationError) as error:
            load(synthetic)
        assert error.value.code == {"invalid_year": "invalid_year",
                                    "invalid_runtime": "invalid_number",
                                    "invalid_principal_id": "invalid_id"}[case]
        return
    result = load(synthetic)
    assert set(result.records) == {1, 2, 3}
    if case == "missing_crew":
        assert result[1].imdb_allowed and result[1].directors is None
        assert "imdb_crew_missing" in result[1].reasons
    elif case == "missing_actor_name":
        assert result[1].imdb_allowed and result[1].actors[0].name is None
        assert result[1].actors[0].nconst == "nm0000003"
        assert "imdb_person_name_missing" in result[1].reasons
    else:
        assert not result[1].imdb_allowed and result[1].runtime_minutes is None
        assert result[1].actors is None and result.stats["imdb_quarantined"] >= 1


def test_data_005_source_use_gate(synthetic, monkeypatch):
    import recommender.data.imdb_metadata as module
    bridge = mapping(synthetic)
    monkeypatch.setattr(module, "_fingerprint", lambda path: pytest.fail("source opened"))
    with pytest.raises(PermissionError, match="D-08"):
        load_imdb_metadata(bridge, synthetic[1])
    with pytest.raises(PermissionError, match="synthetic evidence"):
        load_imdb_metadata(bridge, DEFAULT_IMDB.parent, source_use=evidence(synthetic[1]))
    monkeypatch.undo()
    wrong = evidence(synthetic[1])
    wrong.expected_sha256[TABLES[0]] = "0" * 64
    with pytest.raises(DataValidationError) as error:
        load_imdb_metadata(bridge, synthetic[1], source_use=wrong)
    assert error.value.code == "source_hash_mismatch"
    gz_table(synthetic[1] / TABLES[0], [("tt0000001", "movie", "Changed", "Changed", "0",
                                         "2001", r"\N", "120", "Drama")])
    with pytest.raises(ValueError, match="not bound"):
        load_imdb_metadata(bridge, synthetic[1], source_use=evidence(synthetic[1]))


def test_data_005_links_collision_preserves_movies_and_ratings(synthetic):
    ml = synthetic[0]
    ratings_before = (ml / "ratings.csv").read_bytes()
    csv_table(ml / "links.csv", ("movieId", "imdbId", "tmdbId"),
              [(1, "0000001", "10"), (2, "0000001", "20"), (3, "", "")])
    result = load(synthetic)
    assert set(result.records) == {1, 2, 3}
    assert not result[1].imdb_allowed and not result[2].imdb_allowed
    assert result[1].runtime_minutes is result[2].runtime_minutes is None
    assert result.stats["imdb_quarantined"] == 2
    assert (ml / "ratings.csv").read_bytes() == ratings_before


def test_data_005_offline(synthetic, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("network call"))
    assert load(synthetic)[1].imdb_allowed
