# DATA-001: MovieLens raw table loaders

Slides 3–5. `MovieLens(root)` reuses the existing files under
`dataset_linkage_work/raw/movielens/ml-25m/`. It never downloads, writes, sorts,
filters, deduplicates or deletes raw records. No pandas/runtime dependency is added.
The existing `verify_raw_data.inspect_csv` is reused in the local acceptance preflight;
its report-writing `verify()` and acquisition entrypoints are not called.

```python
from recommender.data import MovieLens, batches, validate_movielens

data = MovieLens()  # Put the repository's src/ on Python's import path.
movie_ids = {movie.movie_id for movie in data.movies()}
for batch in batches(data.ratings(movie_ids=movie_ids), size=50_000):
    # Consume/persist each bounded batch outside raw/; do not list all batches.
    pass
# Optional full read-only audit; returns aggregate counts and raw hashes.
report = validate_movielens()
```

Each immutable, slotted row includes source file, logical CSV record number
(header=1), and physical start/end lines. Combine the file/record key with the audit SHA-256
snapshot for version-bound provenance. Quoted commas, multiline text, UTF-8/BOM
and reordered headers work. Required columns must be unique and exact: schema drift,
bad CSV, wrong row width, invalid IDs, malformed numeric values and unsupported UTC
timestamps fail with deterministic code/field/location, without echoing user values.

MovieLens user/movie IDs are positive signed-64-bit integers. Ratings are exactly
0.5–5.0 in half-star steps. Unix seconds become timezone-aware UTC datetime values,
independent of machine timezone, and must lie from epoch through year 9999. Later
tasks establish historical cutoffs; loading does not imply temporal eligibility.
Movie titles/tags and genre strings retain source text (genres become an ordered
tuple). `(no genres listed)` is retained. Blank tag text is preserved and counted,
not silently dropped. Blank external IDs become None; IMDb digits retain leading
zeros. External identity normalization/joins belong to DATA-002.

`movies()`/`links()` reject duplicate movie keys. Event iterators can check supplied
movie/user ID collections. The full audit requires links for every movie, all event
movies in movies.csv and tag users in the rating-user population. It reports source
hashes, counts, missing external IDs, blank tags and UTC ranges. Source SHA-256,
size and mtime must match before/after the scan. Iterators also detect source stat
changes while open. Exhaust or close partially consumed iterators promptly.

Ratings/tags streaming memory is O(batch size), without a dense matrix or retained
25M-event list. Full audit memory is O(unique movies + unique rating users), using
only ID sets and aggregate counters. Duplicate event payloads remain distinct by
source provenance; global duplicate semantics, broader data quality, provenance
rights, enrichment, research and temporal splitting remain later tasks.

Run all acceptance cases from repository root:
`python -B -m pytest -q tests/data/test_data_001.py`. Synthetic files cover malformed
records, schema, references, provenance, laziness and read-only behavior. A bounded
local-source case reuses the existing header checker and verifies real raw hashes;
CI skips this case when data is absent and never downloads datasets. Full real-data
audit evidence is ignored under `.runtime/evidence/DATA-001/`.

## DATA-002: ID mapping

`build_movie_id_mapping()` reads `movies.csv` and `links.csv` with DATA-001's
loaders, streams the existing IMDb `title.basics.tsv.gz` and TMDb
`movie_details.jsonl`, and returns a `MovieIdMapping`. It opens no ratings,
tags or external user tables. It makes no title or user ID joins, performs no
downloads, and never writes raw data. Callers can pass alternate source paths
for synthetic fixtures.

```python
from recommender.data import build_movie_id_mapping

mapping = build_movie_id_mapping()
item = mapping[1]  # MovieLens movieId
print(item.imdb_id, item.imdb_tconst, item.tmdb_id)
print(mapping.stats, mapping.unmatched_imdb_ids[:5])
```

`imdb_id` preserves the numeric text in `links.csv`, including leading zeros;
`imdb_tconst` adds `tt` and pads to at least seven digits without truncation.
TMDb IDs are positive integers. Each record exposes MovieLens row provenance
and, where a unique consistent match exists, IMDb/TMDb metadata row provenance.
`sources` binds the four input paths to SHA-256, size and mtime; before/after
fingerprints must agree. IMDb metadata lookup retains only targeted title IDs;
TMDb JSONL retains only IDs and source locations, not payloads.

Missing IDs remain `None`. A missing external record is listed under
`unmatched_imdb_ids` or `unmatched_tmdb_ids`. Reused external IDs, duplicate
metadata IDs and contradictory TMDb envelope/provider IDs appear in `issues`
and `stats`. Their metadata source is withheld and the affected record's
`*_conflict` flag is true. No arbitrary winner is selected. Coverage rates
always use the MovieLens movie count as denominator; metadata counts exclude
ambiguous joins. Existing external snapshots do not prove historical
availability at a rating timestamp and must not enter strict temporal features
without later evidence and policy approval.
