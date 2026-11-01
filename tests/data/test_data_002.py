"""DATA-002 acceptance: key-only linkage, explicit missingness, no user joins."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data import DataValidationError, MovieLens, build_movie_id_mapping, normalize_imdb_id
from recommender.data.id_mapping import DEFAULT_IMDB, DEFAULT_TMDB


def csv_table(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def imdb_table(path, ids):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["tconst", "titleType", "primaryTitle"])
        for key in ids:
            writer.writerow([key, "movie", "Same Title"])


def tmdb_entry(movie, tmdb, imdb=None, *, provider_id=None, provider_imdb=None):
    return {"movieId": movie, "tmdbId": tmdb,
            "imdbId": imdb, "userId": 999999,
            "data": {"id": tmdb if provider_id is None else provider_id,
                     "imdb_id": provider_imdb,
                     "title": "Same Title", "userId": 1}}


def tmdb_table(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def build(raw):
    ml, imdb, tmdb = raw
    return build_movie_id_mapping(ml, imdb, tmdb)


@pytest.fixture
def raw(tmp_path):
    ml = tmp_path / "ml"
    ml.mkdir()
    csv_table(ml / "movies.csv", ["movieId", "title", "genres"],
              [(1, "Same Title", "Drama"), (2, "Same Title", "Drama"),
               (3, "Other", "Comedy"), (4, "Missing", "Comedy")])
    csv_table(ml / "links.csv", ["movieId", "imdbId", "tmdbId"],
              [(1, "0000001", "10"), (2, "0000002", "20"),
               (3, "", "30"), (4, "0000004", "")])
    imdb = tmp_path / "title.basics.tsv.gz"
    imdb_table(imdb, ["tt0000001", "tt0000002"])
    tmdb = tmp_path / "movie_details.jsonl"
    tmdb_table(tmdb, [tmdb_entry(1, 10, 1, provider_imdb="tt0000001"),
                      tmdb_entry(2, 20, 2, provider_imdb="tt0000002")])
    return ml, imdb, tmdb


@pytest.mark.parametrize("case", ["key_join", "leading_zeros", "source_provenance",
                                  "coverage", "long_tconst", "order_independent"])
def test_data_002_ac_01(raw, case):
    """Join by movieId/declared external IDs only, with one record per movie."""
    ml, imdb, tmdb = raw
    if case == "long_tconst":
        assert normalize_imdb_id("00012345678") == "tt00012345678"
        assert normalize_imdb_id("1") == "tt0000001"
        assert normalize_imdb_id(None) is None
        return
    if case == "order_independent":
        tmdb_table(tmdb, [tmdb_entry(2, 20, 2, provider_imdb="tt0000002"),
                          tmdb_entry(1, 10, 1, provider_imdb="tt0000001")])
    result = build(raw)
    if case == "key_join":
        assert set(result.records) == {1, 2, 3, 4}
        assert result[1].imdb_tconst == "tt0000001"
        assert result[2].imdb_tconst == "tt0000002"
        assert result[1].tmdb_id == 10 and result[2].tmdb_id == 20
        assert result[3].imdb_tconst is None
        assert result[4].tmdb_id is None
        assert result[1].tmdb_metadata_source is not None
        assert result[2].tmdb_metadata_source is not None
    elif case == "leading_zeros":
        assert result[1].imdb_id == "0000001"
        assert type(result[1].imdb_id) is str
        assert type(result[1].tmdb_id) is int
    elif case == "source_provenance":
        assert result[1].movie_source.source_file == str(ml / "movies.csv")
        assert result[1].link_source.record_number == 2
        assert result[1].imdb_metadata_source.record_number == 2
        assert result[1].tmdb_metadata_source.line_start == 1
        assert set(result.sources) == {str(ml / "movies.csv"), str(ml / "links.csv"),
                                       str(imdb), str(tmdb)}
        assert all(len(source["sha256"]) == 64 for source in result.sources.values())
    elif case == "coverage":
        assert result.stats["movies"] == result.stats["links"] == 4
        assert result.stats["imdb_ids_present"] == 3
        assert result.stats["tmdb_ids_present"] == 3
        assert result.stats["imdb_metadata_matched"] == 2
        assert result.stats["tmdb_metadata_matched"] == 2
        assert result.stats["imdb_id_coverage"] == 0.75
        assert result.stats["imdb_metadata_coverage"] == 0.5
        assert result.unmatched_imdb_ids == ("tt0000004",)
        assert result.unmatched_tmdb_ids == (30,)
    elif case == "order_independent":
        assert result[1].tmdb_metadata_source.line_start == 2
        assert result[2].tmdb_metadata_source.line_start == 1


@pytest.mark.parametrize("case", [
    "null_ids", "missing_imdb_metadata", "missing_tmdb_metadata", "imdb_collision",
    "tmdb_collision", "duplicate_imdb_metadata", "duplicate_tmdb_metadata",
    "provider_id_conflict", "provider_imdb_conflict", "envelope_imdb_conflict",
    "envelope_movie_conflict", "unknown_tmdb_envelope", "duplicate_link",
    "unknown_link", "missing_link", "invalid_link_imdb", "invalid_link_tmdb",
    "invalid_imdb_tconst", "invalid_tmdb_id", "invalid_tmdb_json", "invalid_tmdb_data",
    "invalid_imdb_schema", "invalid_imdb_width", "read_only", "real_sources",
])
def test_data_002_ac_02(raw, case):
    """Missing, invalid, duplicate and conflicting identifiers are deterministic."""
    if case == "real_sources":
        if not (Path("dataset_linkage_work/raw/movielens/ml-25m/links.csv").is_file()
                and DEFAULT_IMDB.is_file() and DEFAULT_TMDB.is_file()):
            pytest.skip("Local raw datasets are unavailable in this checkout")
        result = build_movie_id_mapping()
        movie_count = sum(1 for _ in MovieLens().movies())
        assert result.stats["movies"] == result.stats["links"] == movie_count
        assert result.stats["missing_imdb_ids"] + result.stats["imdb_ids_present"] == movie_count
        assert result.stats["missing_tmdb_ids"] + result.stats["tmdb_ids_present"] == movie_count
        assert result.stats["tmdb_collision_ids"] >= 1
        assert result[1].imdb_id == "0114709"
        assert result[1].imdb_tconst == "tt0114709"
        assert result[1].tmdb_id == 862
        return
    ml, imdb, tmdb = raw
    expected_error = None
    if case == "null_ids":
        csv_table(ml / "links.csv", ["movieId", "imdbId", "tmdbId"],
                  [(1, "", ""), (2, "0000002", "20"),
                   (3, "", "30"), (4, "0000004", "")])
        tmdb_table(tmdb, [tmdb_entry(2, 20, 2, provider_imdb="tt0000002")])
    elif case == "missing_imdb_metadata":
        imdb_table(imdb, ["tt0000001"])
    elif case == "missing_tmdb_metadata":
        tmdb_table(tmdb, [tmdb_entry(1, 10, 1)])
    elif case == "imdb_collision":
        csv_table(ml / "links.csv", ["movieId", "imdbId", "tmdbId"],
                  [(1, "0000001", "10"), (2, "1", "20"),
                   (3, "", "30"), (4, "0000004", "")])
        tmdb_table(tmdb, [tmdb_entry(1, 10, 1), tmdb_entry(2, 20, 1)])
    elif case == "tmdb_collision":
        csv_table(ml / "links.csv", ["movieId", "imdbId", "tmdbId"],
                  [(1, "0000001", "10"), (2, "0000002", "10"),
                   (3, "", "30"), (4, "0000004", "")])
        tmdb_table(tmdb, [tmdb_entry(1, 10, 1)])
    elif case == "duplicate_imdb_metadata":
        imdb_table(imdb, ["tt0000001", "tt0000001", "tt0000002"])
    elif case == "duplicate_tmdb_metadata":
        tmdb_table(tmdb, [tmdb_entry(1, 10, 1), tmdb_entry(1, 10, 1)])
    elif case == "provider_id_conflict":
        tmdb_table(tmdb, [tmdb_entry(1, 10, 1, provider_id=99)])
    elif case == "provider_imdb_conflict":
        tmdb_table(tmdb, [tmdb_entry(1, 10, 1, provider_imdb="tt0000002")])
    elif case == "envelope_imdb_conflict":
        tmdb_table(tmdb, [tmdb_entry(1, 10, 2)])
    elif case == "envelope_movie_conflict":
        tmdb_table(tmdb, [tmdb_entry(4, 10, 4)])
    elif case == "unknown_tmdb_envelope":
        tmdb_table(tmdb, [tmdb_entry(99, 99, 99)])
    elif case == "duplicate_link":
        with (ml / "links.csv").open("a", encoding="utf-8") as handle:
            handle.write("1,0000001,10\n")
        expected_error = ("duplicate_movieId", "movieId")
    elif case == "unknown_link":
        with (ml / "links.csv").open("a", encoding="utf-8") as handle:
            handle.write("99,0000099,99\n")
        expected_error = ("unknown_movieId", "movieId")
    elif case == "missing_link":
        csv_table(ml / "links.csv", ["movieId", "imdbId", "tmdbId"],
                  [(1, "0000001", "10"), (2, "0000002", "20"), (3, "", "30")])
        expected_error = ("missing_movie_link", "movieId")
    elif case in ("invalid_link_imdb", "invalid_link_tmdb"):
        field = "imdbId" if case.endswith("imdb") else "tmdbId"
        csv_table(ml / "links.csv", ["movieId", "imdbId", "tmdbId"],
                  [(1, "x" if field == "imdbId" else "0000001",
                    "1.5" if field == "tmdbId" else "10"),
                   (2, "0000002", "20"), (3, "", "30"), (4, "0000004", "")])
        expected_error = ("invalid_id", field)
    elif case == "invalid_imdb_tconst":
        imdb_table(imdb, ["nm0000001"])
        expected_error = ("invalid_imdb_id", "tconst")
    elif case == "invalid_tmdb_id":
        tmdb_table(tmdb, [tmdb_entry(1, True, 1)])
        expected_error = ("invalid_id", "tmdbId")
    elif case == "invalid_tmdb_json":
        tmdb.write_text("{bad\n", encoding="utf-8")
        expected_error = ("json_syntax", "record")
    elif case == "invalid_tmdb_data":
        tmdb_table(tmdb, [{"movieId": 1, "tmdbId": 10, "data": None}])
        expected_error = ("schema", "data")
    elif case == "invalid_imdb_schema":
        with gzip.open(imdb, "wt", encoding="utf-8") as handle:
            handle.write("titleType\tprimaryTitle\nmovie\tToy\n")
        expected_error = ("schema", "header")
    elif case == "invalid_imdb_width":
        with gzip.open(imdb, "wt", encoding="utf-8") as handle:
            handle.write("tconst\ttitleType\n" "tt0000001\n")
        expected_error = ("row_width", "record")
    if expected_error:
        with pytest.raises(DataValidationError) as error:
            build(raw)
        assert (error.value.code, error.value.field) == expected_error
        return
    if case == "read_only":
        paths = [ml / "movies.csv", ml / "links.csv", imdb, tmdb]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result = build(raw)
    if case == "null_ids":
        assert result[1].imdb_id is result[1].tmdb_id is None
        assert result.stats["missing_imdb_ids"] == 2
        assert result.stats["missing_tmdb_ids"] == 2
    elif case == "missing_imdb_metadata":
        assert result[2].imdb_metadata_source is None
        assert "tt0000002" in result.unmatched_imdb_ids
    elif case == "missing_tmdb_metadata":
        assert result[2].tmdb_metadata_source is None
        assert 20 in result.unmatched_tmdb_ids
    elif case == "imdb_collision":
        assert result[1].imdb_conflict and result[2].imdb_conflict
        assert result[1].imdb_metadata_source is None
        assert result.stats["imdb_collision_ids"] == 1
        assert any(issue.code == "imdb_id_collision" and issue.movie_ids == (1, 2)
                   for issue in result.issues)
    elif case == "tmdb_collision":
        assert result[1].tmdb_conflict and result[2].tmdb_conflict
        assert result[1].tmdb_metadata_source is None
        assert result.stats["tmdb_collision_ids"] == 1
    elif case == "duplicate_imdb_metadata":
        assert result[1].imdb_conflict and result[1].imdb_metadata_source is None
        assert result.stats["duplicate_imdb_metadata_ids"] == 1
    elif case == "duplicate_tmdb_metadata":
        assert result[1].tmdb_conflict and result[1].tmdb_metadata_source is None
        assert any(issue.code == "duplicate_tmdb_metadata" for issue in result.issues)
    elif case in ("provider_id_conflict", "provider_imdb_conflict",
                  "envelope_imdb_conflict", "envelope_movie_conflict"):
        assert result[1].tmdb_conflict and result[1].tmdb_metadata_source is None
        assert result.stats["conflicting_tmdb_metadata_ids"] == 1
    elif case == "unknown_tmdb_envelope":
        assert any(issue.code == "unmatched_tmdb_envelope" for issue in result.issues)
    elif case == "read_only":
        assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == before


@pytest.mark.parametrize("case", ["no_user_tables", "external_user_poison", "distinct_movie_keys"])
def test_data_002_ac_03(raw, case, monkeypatch):
    """User IDs in MovieLens and external payloads never enter movie linkage."""
    if case == "no_user_tables":
        monkeypatch.setattr(MovieLens, "ratings", lambda *a, **k: pytest.fail("ratings opened"))
        monkeypatch.setattr(MovieLens, "tags", lambda *a, **k: pytest.fail("tags opened"))
    result = build(raw)
    assert len(result.records) == 4
    assert not hasattr(result[1], "user_id")
    assert result[1].movie_id != result[2].movie_id
    assert result[1].imdb_tconst != result[2].imdb_tconst
