# Non-destructive movie metadata cleaning policy

Owner decision **D-CLEAN-2026-11-01** (MovieRec Data Quality Policy). This
checkpoint runs before DATA-006 through DATA-POLICY-001. DATA-QUALITY-001 still
requires DATA-001..006 and D-08, and later checks the complete version-bound
manifest. This policy does not approve external source rights, historical
metadata availability, model training or a temporal split.

## Rules v1: `movie-metadata-quarantine-v1`

1. MovieLens `movies.csv` keys and valid `ratings.csv` rows remain in the base
   catalog and collaborative/hybrid candidate populations. No raw MovieLens,
   IMDb or TMDb file is edited, deleted, downloaded or rewritten. Ratings are
   not deduplicated merely because the same user/movie pair occurs twice.
2. `links.csv` is the sole cross-source bridge. Identical titles, external
   `userId` fields and external user accounts never establish identity.
3. A missing external ID or absent metadata is an explicit feature mask,
   distinct from a contradictory ID. An IMDb or TMDb collision, duplicate
   targeted metadata ID, or contradictory TMDb envelope/provider ID sets the
   affected source's `*_mapping_ambiguous` mask. No arbitrary winner is chosen.
   A conflict in one source does not invalidate an otherwise valid other source.
4. Content/Hybrid feature builders must omit masked **external metadata
   fields** for that movie. They may retain validated MovieLens genres and
   interaction features. The movie and its valid ratings remain available for
   collaborative models, candidate generation and coverage denominators.
5. Invalid MovieLens records fail strict loading. A full-row exclusion may be
   proposed only with the exact `DataValidationError` location/code, source
   SHA-256 and a nonblank justification recorded via
   `document_invalid_row`. That record does not itself delete or skip a row;
   a later versioned decision must explicitly apply it and report before/after
   counts. The current real audit authorizes **zero** raw-row exclusions.

## Impact definitions

`audit_cleaning` streams ratings once and stores only movie counters and user
ID sets. It reports distinct ambiguous movie IDs, their rating count and
distinct rating users. Denominators are all validated MovieLens movies,
ratings and observed rating users. The report compares base movie/rating/user
coverage with collaborative and hybrid candidate coverage (unchanged), and
with the diagnostic subset having **both** valid external metadata sources.
That subset is not an instruction to drop other candidates.

Popularity bias is reported as the affected movies' rating share divided by
their movie share, plus the affected share of the top decile of movies ranked
by observed rating count. The decile has `ceil(10% × movie count)` items;
movieId breaks ties. These are descriptive snapshot metrics, not training
features or a historical cutoff. User counts are aggregate only. No user-level
report is written.

The read-only local audit is reproducible from the repository root:

```powershell
$env:PYTHONPATH = 'src'
.\.venv-sdlc\Scripts\python.exe -X utf8 -B -m recommender.data.cleaning
```

It writes only `.runtime/evidence/DATA-POLICY-001/impact.json`, an ignored
aggregate report. MovieLens and external source SHA-256/size/mtime are checked
before and after analysis. The report's `rules_version` and source hashes bind
its numbers to this policy and the observed local files. DATA-QUALITY-001 must
verify its own full manifest and source-specific rights/availability before
research or feature use. Tests use synthetic fixtures and do not edit raw data.
