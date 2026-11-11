"""DATA-006 integration regression: exercise actual builder with synthetic MovieLens.

All external enrichment functions are patched: the test makes no API requests,
never reads real IMDb/TMDb data, and proves source files remain unchanged.
"""
from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data import movie_feature as target
from recommender.data.id_mapping import MovieIdRecord
from recommender.data.movielens import SourceRow


def test_data_006_builder_cross_source_integration(tmp_path, monkeypatch):
    ml = tmp_path / "movielens"
    ml.mkdir()
    text = {
        "movies.csv": "movieId,title,genres\n1,One,Drama\n2,Two,Action\n3,Three,Comedy\n",
        "links.csv": "movieId,imdbId,tmdbId\n1,1,11\n2,2,22\n3,,\n",
        "ratings.csv": "userId,movieId,rating,timestamp\n1,1,4.5,100\n1,2,3.0,101\n2,3,4.0,102\n",
        "tags.csv": "userId,movieId,tag,timestamp\n1,1,Great,103\n",
    }
    for name, contents in text.items():
        (ml / name).write_bytes(contents.encode("utf-8"))
    before_bytes = {name: (ml / name).read_bytes() for name in text}

    source = SourceRow(str(ml / "movies.csv"), 2, 2, 2)
    link = SourceRow(str(ml / "links.csv"), 2, 2, 2)
    mapping = SimpleNamespace(
        records={
            1: MovieIdRecord(1, "1", "tt0000001", 11, source, link, source,
                             source, False, False),
            2: MovieIdRecord(2, "2", "tt0000002", 22, source, link, None,
                             source, True, False),
            3: MovieIdRecord(3, None, None, None, source, link, None,
                             None, False, False),
        },
        issues=(), sources={},
    )
    calls = {}

    def fake_mapping(root, imdb_path, tmdb_path):
        calls["mapping"] = (Path(root), Path(imdb_path), Path(tmdb_path))
        return mapping

    def fake_imdb(source_mapping, directory, *, source_use):
        calls["imdb"] = (source_mapping, directory, source_use)
        return SimpleNamespace(
            records={
                1: SimpleNamespace(imdb_allowed=True, reasons=(), genres=("Drama", "Mystery"),
                                   runtime_minutes=121, release_year=2021,
                                   directors=(SimpleNamespace(name="IMDB Director"),),
                                   actors=(SimpleNamespace(name="IMDB Actor"),)),
                2: SimpleNamespace(imdb_allowed=False, reasons=("imdb_mapping_ambiguous",),
                                   genres=None, runtime_minutes=None, release_year=None,
                                   directors=None, actors=None),
            }, issues=(), sources={},
        )

    def fake_tmdb(source_mapping, directory, *, source_use):
        calls["tmdb"] = (source_mapping, directory, source_use)
        return SimpleNamespace(
            records={
                1: SimpleNamespace(tmdb_allowed=True, reasons=(), overview="First plot",
                                   keywords=(SimpleNamespace(name="mystery"),),
                                   cast=(SimpleNamespace(name="TMDB Actor"),),
                                   crew=(SimpleNamespace(name="TMDB Director", role="Director"),),
                                   release_date=date(2020, 1, 2)),
                2: SimpleNamespace(tmdb_allowed=True, reasons=(), overview="Second plot",
                                   keywords=(), cast=(), crew=(), release_date=None),
            }, issues=(), sources={},
        )

    monkeypatch.setattr(target, "build_movie_id_mapping", fake_mapping)
    monkeypatch.setattr(target, "load_imdb_metadata", fake_imdb)
    monkeypatch.setattr(target, "load_tmdb_metadata", fake_tmdb)

    evidence_imdb = object()
    evidence_tmdb = object()
    records, provenance, issues = target.build_movie_feature_store(
        ml, tmp_path / "imdb", tmp_path / "tmdb",
        source_use_imdb=evidence_imdb, source_use_tmdb=evidence_tmdb,
    )

    assert set(records) == {1, 2, 3}
    assert calls["mapping"][1].name == "title.basics.tsv.gz"
    assert calls["mapping"][2].name == "movie_details.jsonl"
    assert calls["imdb"][2] is evidence_imdb
    assert calls["tmdb"][2] is evidence_tmdb
    assert records[1].title == "One"
    assert records[1].genres == ("Drama", "Mystery")
    assert records[1].imdb_id == "tt0000001"
    assert records[1].tmdb_id == 11
    assert records[1].runtime_minutes == 121
    assert records[1].release_year == 2021
    assert records[1].director == "TMDB Director"
    assert records[1].cast == ("TMDB Actor",)
    assert records[1].keywords == ("mystery",)
    assert records[1].quarantine_mask == ()

    # IMDb conflict masks only IMDb features; TMDb remains usable.
    assert records[2].title == "Two"
    assert records[2].imdb_id is None
    assert records[2].imdb_allowed is False
    assert records[2].tmdb_allowed is True
    assert records[2].overview == "Second plot"
    assert records[2].quarantine_mask == ("imdb_quarantined",)

    # Missing external IDs is not the same as an ambiguous metadata quarantine.
    assert records[3].title == "Three"
    assert records[3].genres == ("Comedy",)
    assert records[3].quarantine_mask == ()
    assert records[3].imdb_allowed is False
    assert records[3].tmdb_allowed is False
    assert records[3].source_provenance["imdb_missing"] is True

    assert provenance["schema_version"] == target.SCHEMA_VERSION
    assert set(provenance["movielens_sources"]) == set(text)
    assert records[1].source_provenance["schema_version"] == target.SCHEMA_VERSION
    assert issues == ()
    assert {name: (ml / name).read_bytes() for name in text} == before_bytes


def test_data_006_builder_rejects_missing_genome_directory(tmp_path, monkeypatch):
    # The builder must not silently omit a genome source requested by the caller.
    monkeypatch.setattr(target, "source_snapshot", lambda root: {})
    monkeypatch.setattr(target, "build_movie_id_mapping", lambda *a, **k: SimpleNamespace(
        records={}, sources={}, issues=(),
    ))
    monkeypatch.setattr(target, "MovieLens", lambda root: SimpleNamespace(movies=lambda: iter(())))
    import pytest
    with pytest.raises(FileNotFoundError):
        target.build_movie_feature_store(tmp_path, tag_genome_path=tmp_path / "missing")
