"""DATA-004 acceptance tests use synthetic files only; no TMDb API or raw snapshot."""
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data import (
    DataValidationError, SourceUseEvidence, build_movie_id_mapping,
    load_tmdb_metadata,
)
from recommender.data.id_mapping import DEFAULT_TMDB

STAMP = "2026-10-25T12:00:00Z"
TABLES = ("movie_details.jsonl", "keywords.jsonl", "credits.jsonl")


def csv_table(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def row(movie_id, tmdb_id, imdb_id, data, *, stamp=STAMP):
    return {"movieId": movie_id, "tmdbId": tmdb_id, "imdbId": imdb_id,
            "fetched_at_utc": stamp, "data": data}


def details(movie_id, tmdb_id, imdb_id):
    return row(movie_id, tmdb_id, imdb_id, {
        "id": tmdb_id, "imdb_id": f"tt{imdb_id:07d}",
        "overview": "  A story  ", "genres": [{"id": 18, "name": " Drama "}],
        "release_date": "2001-02-03"})


def keywords(movie_id, tmdb_id, imdb_id):
    return row(movie_id, tmdb_id, imdb_id,
               {"keywords": [{"id": 7, "name": " friendship "}]})


def credits(movie_id, tmdb_id, imdb_id):
    return row(movie_id, tmdb_id, imdb_id, {
        "cast": [{"id": 100, "name": " Actor ", "character": " Lead ", "order": 0}],
        "crew": [{"id": 200, "name": " Director ", "job": " Director "}]})


@pytest.fixture
def synthetic(tmp_path):
    ml = tmp_path / "ml"
    tmdb = tmp_path / "tmdb"
    ml.mkdir()
    tmdb.mkdir()
    csv_table(ml / "movies.csv", ("movieId", "title", "genres"),
              [(1, "First", "Drama"), (2, "Second", "Comedy"),
               (3, "No TMDb", "Drama")])
    csv_table(ml / "links.csv", ("movieId", "imdbId", "tmdbId"),
              [(1, "0000001", "10"), (2, "0000002", "20"), (3, "0000003", "")])
    csv_table(ml / "ratings.csv", ("userId", "movieId", "rating", "timestamp"),
              [(9, 1, 4, 100), (9, 2, 5, 200), (8, 3, 3, 300)])
    imdb = tmp_path / "title.basics.tsv.gz"
    with gzip.open(imdb, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(("tconst", "titleType"))
        writer.writerows((("tt0000001", "movie"), ("tt0000002", "movie"),
                          ("tt0000003", "movie")))
    jsonl(tmdb / TABLES[0], [details(1, 10, 1), details(2, 20, 2)])
    jsonl(tmdb / TABLES[1], [keywords(1, 10, 1), keywords(2, 20, 2)])
    jsonl(tmdb / TABLES[2], [credits(1, 10, 1), credits(2, 20, 2)])
    return ml, imdb, tmdb


def evidence(tmdb):
    return SourceUseEvidence(
        source_version="synthetic-v1",
        origin_evidence="generated in pytest fixture",
        permitted_use_evidence="synthetic data with no external rights",
        expected_sha256={name: hashlib.sha256((tmdb / name).read_bytes()).hexdigest()
                         for name in TABLES},
        synthetic_fixture=True,
    )


def mapping(synthetic):
    ml, imdb, tmdb = synthetic
    return build_movie_id_mapping(ml, imdb, tmdb / TABLES[0])


def load(synthetic):
    tmdb = synthetic[2]
    return load_tmdb_metadata(mapping(synthetic), tmdb, source_use=evidence(tmdb))


def test_data_004_ac_01(synthetic):
    ml, _, tmdb = synthetic
    ratings_before = (ml / "ratings.csv").read_bytes()
    result = load(synthetic)
    one = result[1]
    assert set(result.records) == {1, 2, 3}
    assert one.tmdb_allowed and one.tmdb_id == 10 and one.imdb_id == "0000001"
    assert one.overview == "A story" and one.genres[0].name == "Drama"
    assert one.genres[0].source_id == 18
    assert one.keywords[0].name == "friendship" and one.keywords[0].source_id == 7
    assert (one.cast[0].source_id, one.cast[0].name, one.cast[0].role,
            one.cast[0].order) == (100, "Actor", "Lead", 0)
    assert (one.crew[0].source_id, one.crew[0].role) == (200, "Director")
    assert one.release_date == date(2001, 2, 3)
    assert one.fetched_at_utc == datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    assert set(one.source_rows) == set(TABLES)
    assert one.source_rows[TABLES[0]].record_number == 1
    assert result[3].tmdb_id is None and result[3].overview is None
    assert "tmdb_id_missing" in result[3].reasons
    assert result.stats["movies"] == 3 and result.stats["tmdb_allowed"] == 2
    assert result.stats["movie_details_rows"] == 2
    assert result.stats["credits_unmatched_rows"] == 0
    assert result.stats["overview_movies"] == result.stats["keywords_movies"] == 2
    assert result.stats["tmdb_coverage"] == 2 / 3
    assert "interaction times" in result.temporal_warning
    assert result.source_use.source_version == "synthetic-v1"
    assert {path.name for path in map(Path, result.sources)} == set(TABLES)
    assert (ml / "ratings.csv").read_bytes() == ratings_before
    assert all(hashlib.sha256((tmdb / name).read_bytes()).hexdigest()
               == result.sources[str(tmdb / name)]["sha256"] for name in TABLES)


@pytest.mark.parametrize("case", [
    "missing_details", "missing_keywords", "missing_credits", "null_fields",
    "missing_person_name", "missing_facet_name",
    "duplicate_details", "duplicate_keywords", "duplicate_credits",
    "duplicate_genre_facet", "duplicate_keyword_facet",
    "conflicting_movie", "conflicting_imdb", "conflicting_provider",
    "conflicting_fetch_time", "unmatched_external", "invalid_date", "invalid_cast", "bad_json",
])
def test_data_004_ac_02(synthetic, case):
    ml, imdb, tmdb = synthetic
    if case == "missing_details":
        jsonl(tmdb / TABLES[0], [details(1, 10, 1)])
    elif case == "missing_keywords":
        jsonl(tmdb / TABLES[1], [keywords(1, 10, 1)])
    elif case == "missing_credits":
        jsonl(tmdb / TABLES[2], [credits(1, 10, 1)])
    elif case == "null_fields":
        item = details(1, 10, 1)
        item["data"].update(overview=None, genres=None, release_date="")
        jsonl(tmdb / TABLES[0], [item, details(2, 20, 2)])
    elif case == "missing_person_name":
        item = credits(1, 10, 1)
        item["data"]["crew"][0]["name"] = None
        jsonl(tmdb / TABLES[2], [item, credits(2, 20, 2)])
    elif case == "missing_facet_name":
        item = keywords(1, 10, 1)
        item["data"]["keywords"][0]["name"] = ""
        jsonl(tmdb / TABLES[1], [item, keywords(2, 20, 2)])
    elif case == "duplicate_details":
        jsonl(tmdb / TABLES[0], [details(1, 10, 1), details(2, 20, 2), details(1, 10, 1)])
    elif case in ("duplicate_keywords", "duplicate_credits"):
        table = TABLES[1] if case == "duplicate_keywords" else TABLES[2]
        make = keywords if case == "duplicate_keywords" else credits
        jsonl(tmdb / table, [make(1, 10, 1), make(2, 20, 2), make(1, 10, 1)])
    elif case in ("duplicate_genre_facet", "duplicate_keyword_facet"):
        table = TABLES[0] if case == "duplicate_genre_facet" else TABLES[1]
        make = details if case == "duplicate_genre_facet" else keywords
        field = "genres" if case == "duplicate_genre_facet" else "keywords"
        item = make(1, 10, 1)
        item["data"][field].append(dict(item["data"][field][0]))
        jsonl(tmdb / table, [item, make(2, 20, 2)])
    elif case in ("conflicting_movie", "conflicting_imdb", "conflicting_provider",
                  "conflicting_fetch_time"):
        item = keywords(1, 10, 1)
        if case == "conflicting_movie": item["movieId"] = 2
        if case == "conflicting_imdb": item["imdbId"] = 2
        if case == "conflicting_provider": item["data"]["id"] = 99
        if case == "conflicting_fetch_time": item["fetched_at_utc"] = "2026-10-26T00:00:00Z"
        jsonl(tmdb / TABLES[1], [item, keywords(2, 20, 2)])
    elif case == "invalid_date":
        item = details(1, 10, 1)
        item["data"]["release_date"] = "2001-02-30"
        jsonl(tmdb / TABLES[0], [item, details(2, 20, 2)])
    elif case == "invalid_cast":
        item = credits(1, 10, 1)
        item["data"]["cast"][0]["order"] = -1
        jsonl(tmdb / TABLES[2], [item, credits(2, 20, 2)])
    elif case == "unmatched_external":
        jsonl(tmdb / TABLES[1], [keywords(1, 10, 1), keywords(2, 20, 2),
                                 keywords(99, 99, 99)])
    else:
        (tmdb / TABLES[1]).write_text("{bad\n", encoding="utf-8")

    if case in ("invalid_date", "invalid_cast", "bad_json"):
        with pytest.raises(DataValidationError) as error:
            load(synthetic)
        assert error.value.code == {"invalid_date": "invalid_date",
                                    "invalid_cast": "invalid_order",
                                    "bad_json": "json_syntax"}[case]
        return
    result = load(synthetic)
    if case == "missing_details":
        assert not result[2].tmdb_allowed and result[2].overview is None
        assert "tmdb_metadata_missing" in result[2].reasons
    elif case == "missing_keywords":
        assert result[2].tmdb_allowed and result[2].keywords is None
        assert "tmdb_keywords_missing" in result[2].reasons
    elif case == "missing_credits":
        assert result[2].tmdb_allowed and result[2].cast is result[2].crew is None
        assert "tmdb_credits_missing" in result[2].reasons
    elif case == "null_fields":
        assert result[1].tmdb_allowed and result[1].overview is None
        assert result[1].genres is None and result[1].release_date is None
    elif case == "missing_person_name":
        assert result[1].tmdb_allowed and result[1].crew[0].name is None
        assert result[1].crew[0].source_id == 200
    elif case == "missing_facet_name":
        assert result[1].tmdb_allowed and result[1].keywords[0].name is None
        assert result[1].keywords[0].source_id == 7
    elif case == "unmatched_external":
        assert result[1].tmdb_allowed and result[2].tmdb_allowed
        assert result.stats["keywords_unmatched_rows"] == 1
    else:
        assert not result[1].tmdb_allowed and result[1].overview is None
        assert result[1].cast is None and result[1].keywords is None
        assert result[2].tmdb_allowed
        assert result.stats["tmdb_quarantined"] >= 1
        if case == "duplicate_details":
            assert any(issue[0] == "duplicate_tmdb_metadata" for issue in result.issues)
        if case in ("duplicate_genre_facet", "duplicate_keyword_facet"):
            assert any(issue[0] == "tmdb_duplicate_facet_id" for issue in result.issues)
    assert set(result.records) == {1, 2, 3}


def test_data_004_ac_03(synthetic, monkeypatch):
    ml, imdb, tmdb = synthetic
    bridge = mapping(synthetic)
    # The use gate precedes hashing/opening any TMDb input.
    import recommender.data.tmdb_metadata as module
    monkeypatch.setattr(module, "_fingerprint", lambda path: pytest.fail("source opened"))
    with pytest.raises(PermissionError, match="D-08"):
        load_tmdb_metadata(bridge, tmdb)
    with pytest.raises(PermissionError, match="synthetic evidence"):
        load_tmdb_metadata(bridge, DEFAULT_TMDB.parent, source_use=evidence(tmdb))
    monkeypatch.undo()
    bad = evidence(tmdb)
    bad.expected_sha256[TABLES[0]] = "0" * 64
    with pytest.raises(DataValidationError) as error:
        load_tmdb_metadata(bridge, tmdb, source_use=bad)
    assert error.value.code == "source_hash_mismatch"
    # A changed details file must not be joined to a mapping built from older bytes.
    jsonl(tmdb / TABLES[0], [details(1, 10, 1), details(2, 20, 2),
                             details(999, 999, 999)])
    with pytest.raises(ValueError, match="not bound"):
        load_tmdb_metadata(bridge, tmdb, source_use=evidence(tmdb))


def test_data_004_ac_03_offline(synthetic, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("network call"))
    result = load(synthetic)
    assert result[1].tmdb_allowed
