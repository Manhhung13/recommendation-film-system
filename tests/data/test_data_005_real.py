"""Opt-in read-only validation of owner-attested local IMDb enrichment.

Hashes bind the owner attestations recorded in the DATA-005 README to the
current local snapshot. No network request or raw-data write occurs.
"""
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data import (
    ImdbSourceUseEvidence, build_movie_id_mapping, load_imdb_metadata,
)
from recommender.data.id_mapping import _fingerprint

ML = ROOT / "dataset_linkage_work/raw/movielens/ml-25m"
IMDB = ROOT / "dataset_linkage_work/raw/imdb"
TMDB_DETAILS = ROOT / "dataset_linkage_work/raw/tmdb/movie_details.jsonl"
EXPECTED = {
    ML / "movies.csv": "c50dea6973e619f9bc1decd4afa3e35358b83a5fb663dac0ec82252a011d023d",
    ML / "links.csv": "dd07bbd9aa8e76d263d8323ddd18ec87b6e00a79a68a5896afe9a737af22322b",
    IMDB / "title.basics.tsv.gz": "a651030038a352ba561b3d625f1d41eeafaa2b4f62d86260bf95163bce33675f",
    IMDB / "title.crew.tsv.gz": "baac8386081d10a1c3b3dc9206ed172f608721d8525b279018499256b5caeca1",
    IMDB / "title.principals.tsv.gz": "f6e74f145c2e8fadfa6bd7d3c450ecac2cfd6035a37c6b6d3b2a8f0301b7c45a",
    IMDB / "name.basics.tsv.gz": "28b568fe1a88f73ffa59ad48652f2b6ce736fb57da805ff3a219d7d30737f4d8",
    TMDB_DETAILS: "c25475b00ba88c9e03f21deab616e9e3c8019da4a2a0b7bdc90db7b30b1d7c57",
}


@pytest.mark.skipif(os.getenv("MOVIEREC_DATA_005_REAL") != "1",
                    reason="explicit D-08 local source-use validation only")
def test_data_005_attested_local_read_only():
    before = {path: _fingerprint(path) for path in EXPECTED}
    assert {path: info["sha256"] for path, info in before.items()} == EXPECTED
    mapping = build_movie_id_mapping(ML, IMDB / "title.basics.tsv.gz", TMDB_DETAILS)
    use = ImdbSourceUseEvidence(
        source_version="hash-bound local IMDb daily export; exact export date not evidenced",
        origin_evidence="2026-11-05 owner attestations: four files from official IMDb downloadable datasets",
        permitted_use_evidence="2026-11-05 owner attestations: D-08 private non-commercial research",
        expected_sha256={path.name: digest for path, digest in EXPECTED.items()
                         if path.parent == IMDB},
    )
    enrichment = load_imdb_metadata(mapping, IMDB, source_use=use)
    assert set(enrichment.records) == set(mapping.records)
    assert enrichment.stats["movies"] == mapping.stats["movies"]
    assert enrichment.stats["imdb_allowed"] <= enrichment.stats["movies"]
    assert all(row.movie_id == movie_id for movie_id, row in enrichment.records.items())
    after = {path: _fingerprint(path) for path in EXPECTED}
    assert before == after
    print("DATA-005_LOCAL_COVERAGE=" + json.dumps(dict(enrichment.stats), sort_keys=True))
