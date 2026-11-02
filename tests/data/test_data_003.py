"""DATA-003 acceptance tests: Tag Genome alignment, validation and provenance."""
import csv
from contextlib import closing
import hashlib
from itertools import islice
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data import DataValidationError, MovieLens, load_tag_genome


def table(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def raw(tmp_path):
    table(tmp_path / "movies.csv", ("movieId", "title", "genres"),
          [(1, "One", "Drama"), (2, "Two", "Comedy"), (3, "Three", "Drama")])
    # Deliberately shuffled IDs and header columns: position must never be identity.
    table(tmp_path / "genome-tags.csv", ("tag", "tagId"),
          [("space", 9), ("warm", 2), ("noir", 5)])
    table(tmp_path / "genome-scores.csv", ("relevance", "tagId", "movieId"),
          [("0", 9, 1), ("0.5", 2, 1), ("1", 5, 1),
           ("0.25", 5, 2), ("0.75", 9, 2), ("0.125", 2, 2)])
    return tmp_path


def scores(raw, rows, header=("movieId", "tagId", "relevance")):
    table(raw / "genome-scores.csv", header, rows)


def test_data_003_ac_01(raw):
    result = load_tag_genome(raw, source_version="synthetic-v1")
    assert result.tag_ids == (2, 5, 9)
    assert result.tag_positions == {2: 0, 5: 1, 9: 2}
    assert result.tags == {2: "warm", 5: "noir", 9: "space"}
    assert result.relevance(1, 9) == 0
    assert result.relevance(1, 2) == 0.5
    assert result.relevance(1, 5) == 1
    assert result.relevance(2, 2) == 0.125
    assert len(result.movies[1].packed_relevance) == 3 * 8
    assert result.movies[1].observed_tags == 3
    assert result.tag_sources[9].record_number == 2
    assert result.movies[1].first_source.record_number == 2
    assert result.movies[1].last_source.record_number == 4
    with pytest.raises(KeyError):
        result.relevance(1, 999)
    with pytest.raises(KeyError):
        result.relevance(999, 2)


@pytest.mark.parametrize("bad", ["", "NaN", "inf", "-0.1", "+0.1", "1.01",
                                      "1.00000000000000001", "0.5 ", "1e-1",
                                      "0,5", "9" * 129])
def test_data_003_ac_02(raw, bad):
    scores(raw, [(1, 2, bad)])
    with pytest.raises(DataValidationError) as error:
        load_tag_genome(raw)
    assert (error.value.code, error.value.field) == ("invalid_relevance", "relevance")
    assert error.value.source.record_number == 2
    if bad:
        assert bad not in str(error.value)


def test_data_003_ac_02_missingness(raw):
    result = load_tag_genome(raw)
    assert result.missing_movie_ids == (3,)
    assert result.relevance(3, 2) is None
    scores(raw, [(1, 2, "0.5"), (1, 5, "0.75")])
    with pytest.raises(DataValidationError) as error:
        load_tag_genome(raw)
    assert error.value.code == "incomplete_vector"
    partial = load_tag_genome(raw, strict_complete=False)
    assert partial.incomplete_movie_ids == (1,)
    assert partial.missing_movie_ids == (2, 3)
    assert partial.relevance(1, 9) is None
    assert partial.relevance(1, 5) == 0.75


@pytest.mark.parametrize("case,code,field", [
    ("duplicate_tag", "duplicate_tagId", "tagId"),
    ("duplicate_score", "duplicate_score", "tagId"),
    ("unknown_tag", "unknown_tagId", "tagId"),
    ("unknown_movie", "unknown_movieId", "movieId"),
    ("bad_tag", "invalid_text", "tag"),
    ("bad_movie", "invalid_id", "movieId"),
    ("bad_tag_id", "invalid_id", "tagId"),
    ("score_width", "row_width", "record"),
    ("tag_schema", "schema", "header"),
    ("score_syntax", "csv_syntax", "record"),
    ("empty_tags", "empty_table", "record"),
    ("empty_scores", "empty_table", "record"),
])
def test_data_003_ac_03_invalid(raw, case, code, field):
    if case == "duplicate_tag":
        table(raw / "genome-tags.csv", ("tagId", "tag"),
              [(2, "warm"), (5, "noir"), (9, "space"), (2, "other")])
    elif case == "duplicate_score":
        scores(raw, [(1, 2, "0.5"), (1, 2, "0.8")])
    elif case == "unknown_tag":
        scores(raw, [(1, 99, "0.5")])
    elif case == "unknown_movie":
        scores(raw, [(99, 2, "0.5")])
    elif case == "bad_tag":
        table(raw / "genome-tags.csv", ("tagId", "tag"), [(2, " ")])
    elif case == "bad_movie":
        scores(raw, [("-1", 2, "0.5")])
    elif case == "bad_tag_id":
        scores(raw, [(1, "2.0", "0.5")])
    elif case == "score_width":
        scores(raw, [(1, 2)])
    elif case == "tag_schema":
        table(raw / "genome-tags.csv", ("id", "tag"), [(2, "warm")])
    elif case == "score_syntax":
        (raw / "genome-scores.csv").write_text(
            'movieId,tagId,relevance\n1,2,"0.5\n', encoding="utf-8")
    elif case == "empty_tags":
        table(raw / "genome-tags.csv", ("tagId", "tag"), [])
    else:
        scores(raw, [])
    with pytest.raises(DataValidationError) as error:
        load_tag_genome(raw)
    assert (error.value.code, error.value.field) == (code, field)


def test_data_003_ac_03(raw):
    paths = [raw / name for name in
             ("movies.csv", "genome-tags.csv", "genome-scores.csv")]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    result = load_tag_genome(raw, source_version="synthetic-v1")
    assert result.source_version == "synthetic-v1"
    assert result.stats == {"movies": 3, "genome_movies": 2,
                            "missing_movies": 1, "incomplete_movies": 0,
                            "tags": 3, "score_rows": 6,
                            "movie_coverage": 2 / 3}
    assert set(result.sources) == {str(path) for path in paths}
    assert all(result.sources[str(path)]["sha256"] == digest
               for path, digest in before.items())
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths} == before


def test_data_003_ac_03_real_read_only():
    root = ROOT / "dataset_linkage_work/raw/movielens/ml-25m"
    names = ("movies.csv", "genome-tags.csv", "genome-scores.csv")
    if not all((root / name).is_file() for name in names):
        pytest.skip("Local MovieLens Tag Genome is unavailable; no download")
    before = {name: (root / name).stat().st_mtime_ns for name in names}
    data = MovieLens(root)
    movies = {movie.movie_id for movie in data.movies()}
    with closing(data._rows("genome-tags.csv", expected=("tagId", "tag"))) as stream:
        tags = list(stream)
    assert len(tags) > 1000 and all(row[0].isdigit() for row, _ in tags)
    with closing(data._rows("genome-scores.csv", expected=("movieId", "tagId", "relevance"))) as stream:
        sample = list(islice(stream, 2048))
    assert len(sample) == 2048
    assert all(int(row[0]) in movies and 0 <= float(row[2]) <= 1
               for row, _ in sample)
    assert {name: (root / name).stat().st_mtime_ns for name in names} == before
