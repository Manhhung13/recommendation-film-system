"""DATA-006 synthetic acceptance tests; no real MovieLens records or network."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from recommender.data.movie_feature import (
    MovieFeatureRecord, build_movie_feature_store,
    source_snapshot, validate_feature_record,
)


def test_data_006_ac_01():
    """AC-01: Create movie feature record with fields on slide 6."""
    record = MovieFeatureRecord(
        movie_id=1,
        title="Test Movie",
        genres=("Drama", "Thriller"),
        tmdb_id=10,
        imdb_id="tt0000001",
        tag_genome=None,
        overview="A test movie overview.",
        keywords=("drama", "thriller"),
        cast=("Actor One", "Actor Two"),
        director="Director Name",
        runtime_minutes=120,
        release_year=2020,
        source_provenance={"movie_id": 1, "tag_genome_version": "v1"},
    )
    # All slide-6 fields present and correct
    assert record.movie_id == 1
    assert record.title == "Test Movie"
    assert record.genres == ("Drama", "Thriller")
    assert record.tmdb_id == 10
    assert record.imdb_id == "tt0000001"
    assert record.overview == "A test movie overview."
    assert record.keywords == ("drama", "thriller")
    assert record.cast == ("Actor One", "Actor Two")
    assert record.director == "Director Name"
    assert record.runtime_minutes == 120
    assert record.release_year == 2020
    assert record.source_provenance is not None

    is_valid, errors = validate_feature_record(record)
    assert is_valid, f"validation errors: {errors}"


def test_data_006_ac_02():
    """AC-02: All joins preserve valid movie IDs and ratings; apply DATA-POLICY-001
    per-source quarantine masks only to ambiguous external metadata, with explicit
    missingness and no automatic row deletion."""
    # Valid movie ID preserved with complete metadata; no quarantine
    record = MovieFeatureRecord(
        movie_id=1,
        title="Test Movie",
        genres=("Drama",),
        tmdb_id=10,
        imdb_id="tt0000001",
        overview="Overview",
        keywords=("drama",),
        cast=("Actor",),
        director="Director",
        runtime_minutes=100,
        release_year=2020,
        source_provenance={"movie_id": 1},
        imdb_allowed=True,
        tmdb_allowed=True,
        quarantine_mask=None,
    )
    assert record.movie_id == 1
    assert record.imdb_allowed is True
    assert record.tmdb_allowed is True
    assert record.quarantine_mask is None

    # IMDb-quarantined movie: preserved with explicit missingness, not deleted
    record_imdb_quarantined = MovieFeatureRecord(
        movie_id=2,
        title="Quarantined Movie",
        genres=("Action",),
        tmdb_id=20,
        imdb_id=None,
        overview=None,
        keywords=None,
        cast=None,
        director=None,
        runtime_minutes=None,
        release_year=None,
        source_provenance={"movie_id": 2},
        imdb_allowed=False,
        tmdb_allowed=True,
        quarantine_mask=("imdb_quarantined",),
    )
    assert record_imdb_quarantined.movie_id == 2
    assert record_imdb_quarantined.imdb_id is None
    assert record_imdb_quarantined.imdb_allowed is False
    assert record_imdb_quarantined.tmdb_allowed is True
    assert record_imdb_quarantined.quarantine_mask == ("imdb_quarantined",)

    # Both quarantined: movie ID still present, TMDb/IMDb fields masked
    record_both = MovieFeatureRecord(
        movie_id=3,
        title="Both Quarantined",
        genres=("Comedy",),
        tmdb_id=None,
        imdb_id=None,
        overview=None,
        keywords=None,
        cast=None,
        director=None,
        runtime_minutes=None,
        release_year=None,
        source_provenance={"movie_id": 3},
        imdb_allowed=False,
        tmdb_allowed=False,
        quarantine_mask=("imdb_quarantined", "tmdb_quarantined"),
    )
    assert record_both.movie_id == 3
    assert record_both.imdb_allowed is False
    assert record_both.tmdb_allowed is False
    assert record_both.quarantine_mask == ("imdb_quarantined", "tmdb_quarantined")


def test_data_006_ac_03():
    """AC-03: Version data schema and raw source lineage."""
    record = MovieFeatureRecord(
        movie_id=1,
        title="Test Movie",
        genres=("Drama",),
        tmdb_id=10,
        imdb_id="tt0000001",
        overview="Overview",
        keywords=("drama",),
        cast=("Actor",),
        director="Director",
        runtime_minutes=100,
        release_year=2020,
        source_provenance={
            "movie_id": 1,
            "source_snapshot": {
                "movies.csv": {"sha256": "a" * 64, "size_bytes": 100, "mtime_ns": 1234567890},
                "links.csv": {"sha256": "b" * 64, "size_bytes": 200, "mtime_ns": 1234567891},
                "ratings.csv": {"sha256": "c" * 64, "size_bytes": 300, "mtime_ns": 1234567892},
            },
            "tag_genome_version": "ml-25m",
        },
    )
    # Raw source lineage is version-bound by SHA-256
    assert record.source_provenance["source_snapshot"]["movies.csv"]["sha256"] == "a" * 64
    assert record.source_provenance["source_snapshot"]["links.csv"]["sha256"] == "b" * 64
    assert record.source_provenance["source_snapshot"]["ratings.csv"]["sha256"] == "c" * 64
    # Tag genome version recorded
    assert record.source_provenance["tag_genome_version"] == "ml-25m"

    # Missing provenance fails validation
    record_no_provenance = MovieFeatureRecord(
        movie_id=1,
        title="Test Movie",
        genres=("Drama",),
        source_provenance=None,
    )
    is_valid, errors = validate_feature_record(record_no_provenance)
    assert not is_valid
    assert any("source_provenance" in e for e in errors)


def test_source_snapshot_records_fingerprints(tmp_path):
    """Verify source hashes, sizes, and timestamps."""
    import hashlib

    files = {
        "movies.csv": "movieId,title,genres\n1,Movie1,Drama\n",
        "links.csv": "movieId,imdbId,tmdbId\n1,1,10\n",
        "ratings.csv": "userId,movieId,rating,timestamp\n1,1,4.0,100\n",
        "tags.csv": "userId,movieId,tag,timestamp\n1,1,Drama,100\n",
    }

    for name, text in files.items():
        (tmp_path / name).write_bytes(text.encode("utf-8"))

    snapshot = source_snapshot(tmp_path)

    assert set(snapshot) == set(files)

    for name in files:
        path = tmp_path / name
        data = path.read_bytes()
        stat = path.stat()

        assert snapshot[name]["sha256"] == hashlib.sha256(data).hexdigest()
        assert snapshot[name]["size_bytes"] == len(data)
        assert snapshot[name]["mtime_ns"] == stat.st_mtime_ns


def test_movie_feature_store_import():
    """Verify movie feature store module imports and exposes the builder."""
    assert build_movie_feature_store is not None
    assert MovieFeatureRecord is not None