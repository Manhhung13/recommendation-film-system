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

## DATA-003: Tag Genome

`load_tag_genome()` reads the local `ml-25m` `genome-tags.csv` and
`genome-scores.csv` with the DATA-001 CSV parser and aligns scores to
`movies.csv` by MovieLens `movieId`. The stable vocabulary is the sorted
`tagId` tuple; never align by tag text or a position from a different source
version. Each vector stores packed doubles instead of Python float objects.
Missing movie vectors are listed in `missing_movie_ids`; their relevance is
`None`. Incomplete vectors fail by default; `strict_complete=False` permits an
audit result that lists them and returns `None` for omitted scores. Duplicate
keys, bad values, unknown IDs and malformed CSV fail with source locations.

`source_version`, per-file SHA-256/size/mtime in `sources`, vocabulary row
locations and per-movie first/last score rows bind the mapping to its raw
snapshot. This is a read-only ingestion result, not an approval for temporal
feature use. The genome may have been computed from ratings/tags/reviews after
a target interaction; later split and feature tasks must establish leakage-safe
availability before training or evaluation.

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

## DATA-004: TMDb metadata

`load_tmdb_metadata(mapping, tmdb_dir, source_use=...)` streams the existing
movie details, keywords and credits JSONL files. It retains normalized
overview, genres, release date, keywords, cast, crew, source IDs and source row
locations for MovieLens movies. It does not open ratings or contact TMDb.
Source hashes must match explicit `SourceUseEvidence` and the details hash in
the DATA-002 movie mapping before any payload is read; the files are hashed
again after parsing. Missing fields remain `None`. Duplicate or contradictory
TMDb rows withhold the affected movie's TMDb fields under the
`movie-metadata-quarantine-v1` mask, while the MovieLens movie remains present.

`SourceUseEvidence` records a documented origin, permitted-use basis,
version and expected hashes. Supplying an object is an audit assertion, not
proof of an API account or license. D-08's unresolved real-snapshot flags must
be resolved before constructing real-data evidence or calling this loader on
the local snapshot. Synthetic fixtures use `synthetic_fixture=True`; that flag
cannot authorize the repository's raw TMDb directory. Returned fetch times
and source fingerprints preserve provenance, but fetched metadata must not be
used as historical features until a separate temporal leakage review.

The documented acquisition path in `acquire_all_data.py` selects TMDb IDs
from MovieLens `links.csv`, requests each movie with appended keywords and
credits using an environment-provided credential, and writes three JSONL
envelopes with MovieLens IDs and a fetch time. The existing checkpoint and
crawl report both describe a full run ending 2026-10-25: 62,281 target IDs,
61,427 successes, 854 permanent failures and no pending IDs. Those records
and the D-08 SHA-256 values identify the current local snapshot; they do not
independently prove which account made the requests, which terms it accepted,
or that every row was produced by that script. On 2026-11-05 the owner
factually attested in the DATA-004 Codex conversation that this hash-matched
snapshot came through the documented crawl from an authorized TMDb API account,
without later replacement or mixing, and that the applicable account terms
were accepted and permit D-08 private, non-commercial research processing.
The owner also attested that the hash-matched `title.basics.tsv.gz` was obtained
from IMDb's official downloadable datasets and is permitted for that scope.
These attestations resolve the flagged inputs for this limited local validation;
original download receipts, account records and per-row acquisition proof are
still absent. D-08 restrictions and temporal leakage gates remain in force.

The opt-in read-only validation on 2026-11-05 pinned `movies.csv`, `links.csv`,
`title.basics.tsv.gz` and all three TMDb JSONL files to their D-08 SHA-256
values before and after enrichment. It retained 62,423 MovieLens movie IDs;
61,262 had eligible TMDb metadata (98.14%), 201 were quarantined, and each
TMDb JSONL file had 61,427 rows with 162 unmatched to an unambiguous mapping.
Overview was present for 61,165 movies and release date for 61,247. The
validation test prints only aggregate coverage and never opens ratings.

## DATA-005: IMDb metadata

`load_imdb_metadata(mapping, imdb_dir, source_use=...)` streams the four
existing IMDb TSV.GZ files, selecting only the `tt` movie and `nm` person IDs
reachable through the DATA-002 `links.csv` mapping. It retains runtime, start
year, genre labels, director and writer IDs, and ordered actor/actress IDs
with available names. Missing IMDb `\N` values become `None`; missing cast
does not remove the MovieLens movie or any rating. Duplicate or conflicting
IDs quarantine the affected IMDb metadata using the DATA-POLICY-001 mask.
The result records source rows, four pre/post SHA-256 fingerprints, an explicit
source-use assertion, coverage, and a temporal-availability warning.

`acquire_all_data.py` names IMDb's official downloadable dataset endpoint and
the four filenames. That code and matching D-08 hashes identify the intended
method and current copies, but cannot prove the exact download run or export
date. On 2026-11-05 the owner attested in the DATA-004 conversation that this
hash-matched `title.basics.tsv.gz` came from IMDb's official downloadable
datasets and is permitted for D-08's private, non-commercial research. In the
DATA-005 conversation the owner likewise attested to the hash-matched
`title.crew.tsv.gz`, `title.principals.tsv.gz`, and `name.basics.tsv.gz`.
Original download receipts and exact export dates remain unavailable. The
IMDb acknowledgement, no redistribution, no replacement database, and no
public or commercial deployment restrictions in D-08 remain in force.

The opt-in read-only validation on 2026-11-05 pinned the four IMDb files,
MovieLens `movies.csv`/`links.csv`, and the DATA-002 TMDb details input to
their D-08 hashes before and after processing. It retained 62,423 MovieLens
movie IDs; 62,294 had eligible IMDb metadata (99.79%), with no ambiguous
IMDb metadata quarantined in this snapshot. Runtime was available for 62,140,
release year for 62,289, directors for 62,138, writers for 59,063, and actors
for 57,151. The 5,143 eligible movies without actor/actress credits remain
present and explicitly report missing cast. Ratings were never opened.
