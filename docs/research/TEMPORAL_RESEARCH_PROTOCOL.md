# Temporal research protocol — proposed, not executed

D-03, D-04, D-08 and D-09 must be approved before dependent work. No cutoff, rating threshold, cold-user boundary or model is selected by this document.

## Time and catalog

Let `H_u(T) = {(i,r,t): user=u, t<T}`. Parse Unix seconds as UTC; a rating timestamp records a rating event, **not watch time**. A tag event is separately timestamped. Ratings file order is not chronology. Sort `(userId,timestamp,movieId,source_row)` stably; equal-time events form a tied block and cannot predict one another. A sequence is rating-event order, not a viewing session. Never infer dislikes from missing ratings.

Candidate T values must be proposed from **development-period** monthly/yearly interaction and release timelines after EDA eligibility. Compare several T, not one convenient date. Require fixed evaluation horizon h and a development/validation/test calendar approved under D-03. Freeze the final test and its positive-label policy before tuning; validation chooses cutoff/features, test is evaluated once by later model tasks. No test-informed cutoff selection.

Proposed strict eligibility: release interval upper bound `<T`, documented catalog availability `<T`, and every feature's evidence `available_at<T`. Known exact release date uses that day in UTC with explicit date precision; a year-only release is interval `[Jan 1, Dec 31]`, so do not assume Jan 1. Release exactly at T and unknown/contradictory date/availability are excluded from strict eligibility and reported separately. Do not use a user's future interaction to backfill past catalog membership. A movie rating before a reported release is a conflict to quarantine/review, not an automatic date correction.

`HISTORICAL_STRICT` permits only independently evidenced as-of snapshots/events and train-only computations. Current MovieLens movie metadata, links, Genome and current IMDb/TMDb enrichments generally lack verified historical versions. Without evidence, flag unavailable and exclude from strict features/catalog claims, even for an old movie. Report strict feasibility as unknown/limited rather than manufacturing availability. `RETROSPECTIVE_ENRICHED` may use current metadata with release filtering, but must label the availability assumption and compare separately; it cannot claim deployable historical performance. Keep unknown/excluded counts in every denominator. Metadata observed now is not historical proof.

## Per-cutoff report contract (EDA-001 future output)

For each `(T,h,mode,manifest,policy_version)` report:

| Measure | Definition |
|---|---|
| eligible users | Users meeting approved minimum history on H(T); also report all observed/sparse users |
| eligible movies | Catalog/release/availability policy above, before filtering already interacted items |
| history interactions | Raw and valid rating/tag counts t<T, with duplicate/conflict exclusions |
| future positives | Approved positive rating events T≤t<T+h; future labels never enter features |
| evaluable positives | Future positives in eligible catalog and allowed by D-01 filter; report removed repeats/new/unknown items separately |
| coverage | Mapped/release-known/as-of-known/metadata-complete numerators and explicit raw/eligible denominators |
| cohort balance | History-size, tenure, activity, recent/inactive, popularity and metadata-coverage cohorts defined using H(T) |
| conflicts | Before-release ratings, title/year/date disagreements, unknown dates, zero-history cases, ties |
| resources | Row counts, partitions/chunks, peak memory, runtime and rejected rows |

Evaluation features are frozen at T unless a separately approved rolling protocol updates only with events strictly before each query time. Popularity, IDF, vocabularies, normalization, shrinkage priors, neighbors and semantic transforms must use training history only. Genome snapshot availability must be audited separately from when user tags occurred. Current TMDb popularity/votes/revenue and IMDb aggregate ratings cannot be inserted into a historical feature vector.

## Planned synthetic acceptance cases

Not implemented/executed here: empty and one-event users; all users sparse; no future positives; timestamps negative/noninteger/out of source bounds; malformed/missing timestamps; timestamp exactly T; release exactly T; year-only/unknown/conflicting release; future metadata fetch; future tag/Genome snapshot; tied events; future-event append invariance; unknown optional metadata; stable output across chunk sizes/input order; timezone and leap-year boundaries. No dense user-item fixtures are required.

Reproducibility manifest must bind code SHA, raw file hashes/source versions, schema/approved policy versions, T/h, mode, timezone, deterministic seed, environment lock/versions, commands/exit codes, rejected-row reason counts, output hashes, metric denominators and report/dashboard references. Recompute hashes after reading; fail if sources change during a run. Assert summaries/timeline totals/cohorts agree; same manifest/config yields identical sorted aggregate outputs apart from declared run metadata.
