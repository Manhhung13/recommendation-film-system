"""Opt-in, read-only DATA-004 validation of owner-attested local sources.

The exact hashes bind the 2026-11-05 owner attestations documented in the
DATA-004 README to this snapshot. No network, download or raw write occurs.
"""
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data import SourceUseEvidence, build_movie_id_mapping, load_tmdb_metadata
from recommender.data.id_mapping import _fingerprint

ML = ROOT / "dataset_linkage_work/raw/movielens/ml-25m"
IMDB = ROOT / "dataset_linkage_work/raw/imdb/title.basics.tsv.gz"
TMDB = ROOT / "dataset_linkage_work/raw/tmdb"
EXPECTED = {
    ML / "movies.csv": "c50dea6973e619f9bc1decd4afa3e35358b83a5fb663dac0ec82252a011d023d",
    ML / "links.csv": "dd07bbd9aa8e76d263d8323ddd18ec87b6e00a79a68a5896afe9a737af22322b",
    IMDB: "a651030038a352ba561b3d625f1d41eeafaa2b4f62d86260bf95163bce33675f",
    TMDB / "movie_details.jsonl": "c25475b00ba88c9e03f21deab616e9e3c8019da4a2a0b7bdc90db7b30b1d7c57",
    TMDB / "keywords.jsonl": "7e551be62b3df94d19762cbeba347bfa270a51d54fcfc0173d67ffbf771196b2",
    TMDB / "credits.jsonl": "d43df79dd1b5ba1df3d2e7f5d1e6dfcd0cc4bce4edefcbc1c29558c13c773e5c",
}


@pytest.mark.skipif(os.getenv("MOVIEREC_DATA_004_REAL") != "1",
                    reason="explicit local D-08 source-use validation only")
def test_data_004_attested_local_read_only():
    before = {path: _fingerprint(path) for path in EXPECTED}
    assert {path: info["sha256"] for path, info in before.items()} == EXPECTED

    mapping = build_movie_id_mapping(ML, IMDB, TMDB / "movie_details.jsonl")
    evidence = SourceUseEvidence(
        source_version="local TMDb crawl snapshot 2026-10-25; not a TMDb provider version",
        origin_evidence="2026-11-05 owner attestation: authorized account, documented crawl, unchanged snapshot",
        permitted_use_evidence="2026-11-05 owner attestation: accepted TMDb terms permit D-08 private non-commercial research",
        expected_sha256={path.name: digest for path, digest in EXPECTED.items()
                         if path.parent == TMDB},
    )
    enrichment = load_tmdb_metadata(mapping, TMDB, source_use=evidence)
    assert set(enrichment.records) == set(mapping.records)
    assert enrichment.stats["movies"] == mapping.stats["movies"]
    assert enrichment.stats["tmdb_allowed"] <= enrichment.stats["movies"]
    assert all(row.movie_id == movie_id for movie_id, row in enrichment.records.items())
    after = {path: _fingerprint(path) for path in EXPECTED}
    assert before == after
    print("DATA-004_LOCAL_COVERAGE=" + json.dumps(dict(enrichment.stats), sort_keys=True))
