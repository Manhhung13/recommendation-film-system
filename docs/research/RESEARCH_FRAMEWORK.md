> SDLC update D-SDLC-2026-10-31: governance clauses below are superseded by
> docs/agent/DEVELOPMENT_SDLC.md. Tests, Git completion receipts, approved business
> decisions and dataset integrity remain required; signatures/review/CI are optional.

# Preference research framework — planning draft

Local task **SDLC-RESEARCH-PLAN-001** (unregistered governance handoff), slides 2–6, 8, 11. This change registers three future tasks and implements their CLI prerequisite guard. It does **not** execute DATA-QUALITY-001, RESEARCH-001 or EDA-001. All three remain BLOCKED; none is VERIFIED. No models, research aggregates, cutoff selections or findings have been produced.

## Order and decisions

`DATA-001..006 → DATA-QUALITY-001 → RESEARCH-001 → EDA-001 → SPLIT-001`.
SPLIT-001 retains its direct DATA-006 dependency. Ancestors include SETUP-001 and SDLC-INTEGRATION-001. Current runtime records only LOCAL_VERIFIED for integration; no trusted data prerequisite evidence exists. D-03 (split), D-04 (positive labels), D-08 (source use) and D-09 (cold-start) remain unapproved. D-01 controls any later interacted-item filter. Proposed formulas/cohorts do not approve those decisions.

## Planning artifacts

- [Data dictionary](DATA_DICTIONARY.md): observed schemas, source semantics, no measured coverage.
- [Hypotheses](HYPOTHESIS_REGISTRY.yaml): H01–H12; all UNTESTED, evidence empty.
- [Features](FEATURE_RESEARCH_CATALOG.yaml): causal construction and fallback proposals.
- [Temporal protocol](TEMPORAL_RESEARCH_PROTOCOL.md): candidate cutoffs and availability policy.
- [Experiment design](EXPERIMENT_DESIGN.md): future tests/ablations; no training here.
- [Risk register](BIAS_AND_LEAKAGE_RISKS.md): confounding, provenance, leakage and mitigations.
- [Governance handoff](../agent/RESEARCH_PLANNING_REPORT.md): actual checks and blockers.

## Development readiness enforcement

Owner decision D-SDLC-2026-10-31 replaces external signatures/bootstrap and mandatory
review/CI. Follow docs/agent/DEVELOPMENT_SDLC.md. agentctl next/start/run-local
validate all dependency test/Git completion receipts and approved business decisions.
Historical VERIFIED or forged DONE/IMPLEMENT local state never authorizes execution.

DATA-QUALITY-001 produces .runtime/dataset-manifest.json. Its completion receipt
binds that manifest hash. RESEARCH/EDA/SPLIT revalidate source hashes, sizes,
versions, UTC retrieval timestamps and required MovieLens/IMDb/TMDb coverage against
that completed manifest. A new manifest needs renewed DATA-QUALITY completion.

Manifest v1: schema_version=1, raw_root=dataset_linkage_work/raw, files=[...]. Each
entry carries repository-relative path, positive size_bytes, sha256, source family,
source_version and retrieved_at_utc. Six MovieLens CSVs, four IMDb dumps and three
TMDb JSONLs remain mandatory. Stream source bytes without mutation. Manifest hashes
prove identity; DATA-QUALITY acceptance additionally validates row/schema/provenance,
coverage and rights. An approved missing-source policy cannot be inferred silently.

## Future implementation constraints

EDA-001 will reuse `links.csv` normalization and source envelopes. Do not invoke acquisition, `migrate_v2`, `verify_dataset_linkage.main` (downloads/exports) or `verify_raw_data.verify` (writes a report) as read-only EDA shortcuts. Legacy header checks/crawl totals are insufficient readiness proof. Ratings are not ordered by timestamp; use external sorting or partitioned columnar reduction with UTC times and deterministic ties. Chunk CSV/TSV/JSONL; sparse user/movie counters are acceptable. Avoid dense user-item matrices, all-pairs user similarity and global quadratic interactions. Benchmark memory/wall time before selecting partitions.

After eligibility: ignored aggregate dataset/user/movie profiles, monthly/yearly first/last interaction and release timelines, cutoff comparison, cohort affinity/drift/sequence summaries, metadata/conflict/coverage audit, hypothesis evidence, report and aggregate-only dashboard. User-level exports remain restricted and untracked; publish approved aggregates with small-cell suppression. Stable sorting, pinned versions, seeds, UTC boundaries and hashes bind reports to one input manifest. Missing optional features yield coverage flags and narrower cohorts, never default zeros.
