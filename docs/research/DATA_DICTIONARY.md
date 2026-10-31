# Data dictionary — observed schema, unmeasured quality

Planning inventory on 2026-10-31: six MovieLens/Genome CSV headers, four IMDb gzip headers, and **one metadata envelope's keys per TMDb JSONL** were read. This is neither full schema validation nor empirical EDA. Row counts, distinct users/items, missingness, mapping coverage, release conflicts and temporal ranges are **NOT_MEASURED**. A field observed in one payload is not guaranteed in others. Types below are expected source types for future validation, not inferred validity of every local value.

Sources: [MovieLens 25M README](https://files.grouplens.org/datasets/movielens/ml-25m-README.html), [IMDb dataset field definitions](https://data.imdb.com/non-commercial-datasets/), [TMDb movie details](https://developer.themoviedb.org/reference/movie-details). Local envelope construction: root `acquire_all_data.py::staged_rows`. Provider documentation describes expected semantics, not a verified local dataset manifest or historical availability. GroupLens includes rating/tag event times and a snapshot Genome; IMDb documents gzipped TSVs with `\N` nulls. No external user identities are joined.

## Conventions applying to every row

Every field inherits source path, immutable file SHA-256, schema/source version, retrieved time and source-row/JSON location provenance. These are required future manifest fields; current hash/version attestations are **missing**, not assumed from file names/mtime. All coverage/missingness is NOT_MEASURED until DATA-QUALITY-001/EDA-001 run. Report both field-level non-null coverage and item/user/interaction-weighted coverage with denominators. Preserve raw values; derived normalized fields live separately.

Temporal codes: **E** = observed UTC event time (usable only t<T); **S** = snapshot, historical `available_at` unknown without separate evidence; **F** = local fetch timestamp, not historical publication/effective time. Strict historical modeling excludes unknown-availability metadata. Modeling codes: **key**, **target**, **feature**, **audit**, **exclude**. Grouped field names enumerate every observed header/payload key; splitting a group never changes the common missingness/provenance rules.

## MovieLens / Tag Genome

Root `dataset_linkage_work/raw/movielens/ml-25m/`; UTF-8 CSV. Numeric IDs must be validated as positive integers; preserve raw source representation. Joins use only declared keys, not titles.

| File.field(s) | Meaning / expected type | Key / missing treatment | Time / leakage / modeling value |
|---|---|---|---|
| ratings.csv.userId | Dataset-local anonymized user integer | User key shared with tags only; missing/invalid rejected | E; no cross-dataset identity; key |
| ratings.csv.movieId | MovieLens movie integer | FK movies.movieId; missing/invalid/unmatched audited | E; key |
| ratings.csv.rating | Explicit half-star rating, decimal 0.5…5.0 | Reject invalid/nonfinite; unrated absent pairs remain unknown | E; target and prior-history feature, never future target as input |
| ratings.csv.timestamp | Unix seconds since UTC epoch, integer | Required; validate precision/range, duplicates/ties | E; rating event, not watch event; temporal feature |
| tags.csv.userId, movieId | Tagging user/movie integers | Local user/movie FKs, retain composite provenance | E; keys |
| tags.csv.tag | User free text, string | Empty/null explicit; vocabulary/normalization train-only | E event, semantic drift; feature with consent/provenance policy |
| tags.csv.timestamp | Tag-application Unix seconds, integer | Required event time; keep distinct from rating time | E; future tags excluded |
| movies.csv.movieId | MovieLens movie integer | PK, uniqueness validated | S; key |
| movies.csv.title | Display title, often trailing year, string | Missing or parse ambiguity preserved | S; year extraction is uncertain, title join forbidden; audit/display |
| movies.csv.genres | Pipe-delimited genre strings | `(no genres listed)` is unknown metadata; multi-label | S; revised metadata may leak; feature only under mode rules |
| links.csv.movieId | MovieLens movie integer | PK/FK to movies; cardinality checks | S; join key |
| links.csv.imdbId | IMDb numeric portion as source string | Validate digits; derive `tt` + zero-pad to at least 7 digits, never truncate longer IDs; preserve nulls | S; only bridge to IMDb tconst; key |
| links.csv.tmdbId | TMDb movie identifier, nullable numeric text | Validate integer-valued positive ID without float-rounding; missing stays unresolved | S; only bridge to TMDb movie ID; key |
| genome-tags.csv.tagId | Genome vocabulary integer | PK in Genome vocabulary, distinct from free-text tags | S; key |
| genome-tags.csv.tag | Genome semantic descriptor, string | Missing text and duplicate IDs audited | S; vocabulary may encode future information; feature |
| genome-scores.csv.movieId, tagId | Movie/Genome tag integer pair | Composite unique key, FKs to movies/vocabulary | S; Genome subset coverage unknown; keys |
| genome-scores.csv.relevance | Movie-tag relevance, numeric [0,1] | Missing is missing vector component, not zero relevance | S; whole snapshot may use future community knowledge; semantic feature |

`README.txt` and `_archives/ml-25m.zip` are present provenance artifacts, not extra user/event tables. File size or an upstream published total is not a local validation result. Existing `linked_movies` uses float conversion and skipping; that behavior must not be assumed to satisfy future strict ID validation.

## IMDb (all four existing files)

Root `dataset_linkage_work/raw/imdb/`; gzipped UTF-8 TSV; `\N` means missing. Dataset versions/retrieved dates require independent provenance; filesystem mtime is not a provider snapshot version. Join `links.imdbId → tconst`; person IDs join only within IMDb. IMDb people are creators, not MovieLens users.

| File.field(s) | Meaning / expected type | Key / missing treatment | Time / leakage / modeling value |
|---|---|---|---|
| title.basics.tsv.gz.tconst | IMDb title ID, string `tt...` | PK, unique; movie mapping only via links | S; key |
| title.basics.titleType | Format/category string | Unknown explicit; movie vs episode filtering needs policy | S; audit/feature |
| title.basics.primaryTitle, originalTitle | Display/original title strings | Preserve raw Unicode and null | S; current edits may leak; display/audit, no identity join |
| title.basics.isAdult | Boolean encoded 0/1 | Missing not false | S; audit/approved constraint |
| title.basics.startYear | Release/start year, nullable integer | Year precision; not exact release date | S; interval eligibility and decade feature |
| title.basics.endYear | Series end year, nullable integer | Often inapplicable for movies | S; future outcomes, audit/exclude |
| title.basics.runtimeMinutes | Primary runtime, nullable numeric integer | Null/nonpositive/versions audited | S; runtime feature with coverage |
| title.basics.genres | Comma-separated category strings | Unknown explicit; preserve source taxonomy | S; feature, source conflict audit |
| title.crew.tsv.gz.tconst | Title ID string | FK basics; duplicates audited | S; key |
| title.crew.directors, writers | Comma-separated nconst arrays | `\N` unknown, parse to normalized person relations | S; creator features under availability rules |
| title.principals.tsv.gz.tconst, ordering | Title ID and per-title integer order | Composite key; validate uniqueness | S; key/audit, order is not rating relevance |
| title.principals.nconst | Person ID string `nm...` | FK name.basics; missing mappings reported | S; creator key |
| title.principals.category, job | Role category and optional job strings | Null job may be valid; role filtering explicit | S; actor/director/writer selection feature |
| title.principals.characters | Encoded character-name array/string | Nullable JSON text; preserve parse errors | S; optional audit, not core preference feature |
| name.basics.tsv.gz.nconst | Person ID string | PK; no user linkage | S; creator key |
| name.basics.primaryName | Credited name string | Display name, no fuzzy identity join | S; display |
| name.basics.birthYear, deathYear | Nullable integer years | Preserve missing; death may postdate cutoff | S; exclude from core features; leakage/audit |
| name.basics.primaryProfession | Comma-separated professions | Optional current top professions | S; audit/optional enriched-only |
| name.basics.knownForTitles | Comma-separated title IDs | Optional derived current prominence | S; future recognition/popularity leakage; exclude historical features |

IMDb title.ratings, title.akas and title.episode were **not found** in this inventory and are not acquired here. Do not fabricate external ratings, regional release dates or per-user IMDb ratings from the four existing dumps.

## TMDb JSONL envelopes and payloads

Root `dataset_linkage_work/raw/tmdb/`. Each line retains raw `data` and local linkage/fetch provenance. Three files must agree on durable tmdbId completion; checkpoint claims do not substitute for their contents. Current API payloads are S unless an as-of source version is evidenced.

| File.field(s) | Meaning / expected type | Key / missing treatment | Time / leakage / modeling value |
|---|---|---|---|
| all.movieId, imdbId, tmdbId | Local link integers from links.csv | Validate consistency with links; unique source rows per tmdbId/file; unresolved IDs audited | S; key, no title matching |
| all.fetched_at_utc | Local UTC ISO timestamp string | Validate format; missing is missing provenance | F; collection time, not historical available_at; audit |
| all.data | Provider object | Missing/nonobject rejects row; keep unknown keys | S; raw provenance |
| movie_details.data.id, imdb_id | TMDb integer ID; IMDb string ID | Reconcile envelope/provider IDs, preserve conflicts | S; key/audit |
| movie_details.data.title, original_title, tagline, overview | Display/original title and text strings | Null/empty text separate; train-only tokenizer/IDF | S; content features subject to availability; titles no join |
| movie_details.data.release_date | Date string YYYY-MM-DD | Empty/malformed/region uncertainty preserved | S; release eligibility with evidence, not availability proof |
| movie_details.data.runtime | Runtime minutes, nullable integer | Zero/null not observed duration | S; attribute feature |
| movie_details.data.genres | Array of objects `{id,name}` | IDs/taxonomy source-specific; empty not negative | S; multi-label genre feature |
| movie_details.data.original_language | Language code string | Missing/unknown explicit | S; attribute feature |
| movie_details.data.spoken_languages | Objects with language codes/names | Multi-valued; distinguish from original language | S; optional attribute feature |
| movie_details.data.origin_country | Country-code array | Optional; not user nationality | S; optional attribute/audit |
| movie_details.data.production_countries | Country code/name objects | Optional; distinguish from release geography | S; audit/optional feature |
| movie_details.data.production_companies | Company objects id/name/logo_path/origin_country | Optional; do not infer creator/user identity | S; optional enriched feature |
| movie_details.data.belongs_to_collection | Nullable collection object id/name/image paths | Null distinct from known collection membership | S; optional franchise feature, future additions risk |
| movie_details.data.budget, revenue | Monetary numeric values | Zero may mean unknown; currency/versions require documentation | S; revenue future-outcome leakage, exclude historical features; budget audit |
| movie_details.data.popularity, vote_average, vote_count | Current popularity/aggregate audience measures | Missing/zero/count validity audited | S; future audience leakage, exclude historical features |
| movie_details.data.adult, video | Provider boolean flags | Missing distinct from false | S; audit/approved constraints |
| movie_details.data.status | Release/production status string | Mutable and optional | S; do not infer historical catalog membership |
| movie_details.data.homepage, poster_path, backdrop_path | URL/image path strings | Nullable; not downloaded | S; display references, exclude ranking inputs |
| movie_details.data.softcore | Observed extra provider key, contract/type not established | Preserve raw, validate only after provider schema decision | S; exclude; do not invent semantics |
| keywords.data.keywords | Array of keyword objects `{id,name}` | Empty/missing distinguished; source IDs vocabulary | S; semantic features, updated labels may leak |
| credits.data.cast, crew | Arrays of credit objects | Missing/empty separate; potentially partial credits | S; creator features with coverage |
| credits.*.id, name, original_name | TMDb person integer ID and display names | Person IDs within TMDb only; IMDb person linkage not assumed | S; creator key/display |
| credits.*.credit_id | Credit string ID | Credit provenance, not user key | S; key/audit |
| credits.*.adult, gender, known_for_department | Provider personal flags/category fields | Optional/unknown explicit; avoid sensitive preference inferences | S; exclude core user preference features |
| credits.*.popularity, profile_path | Current person prominence and image reference | Optional | S; prominence future leakage; exclude/display |
| credits.cast.cast_id, character, order | Cast credit ID, role string, billing integer order | Optional; billing not completeness or preference | S; role/order audit and approved actor features |
| credits.crew.department, job | Department and role strings | Director/writer extraction uses explicit jobs, missing audited | S; creator features |

Nested child shapes above describe expected provider objects, not a full scan of local children. Any extra keys discovered during future validation must be cataloged rather than silently used. Snapshot `status/release_date` and F times cannot establish when metadata originally became known.

## Non-feature local artifacts and pending validation

`checkpoint.json`, `tmdb_crawl_report.json` and two `_staging/*.json` files are present operational state. They are not authoritative historical features or quality acceptance. `verify_raw_data.py` checks headers and selected ID/crawl consistency and writes `raw_data_report.json`; it does not comprehensively validate timestamps, all rows, ranges, duplicate keys, release conflicts, source rights or as-of availability. No validator/acquisition entrypoint was run for this inventory. DATA-QUALITY-001 must inspect these gaps against a frozen manifest and report malformed/null/coverage/conflict counts before research execution.
