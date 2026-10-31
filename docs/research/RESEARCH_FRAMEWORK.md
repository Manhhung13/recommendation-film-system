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

## Supported readiness enforcement

Run from Git root: `python movie-rec-agent-starter/scripts/agentctl.py <action>` with `validate`, `next`, `start TASK-ID` or `run-local TASK-ID`. `next`, `start` and `run-local` guard DATA-QUALITY-001, RESEARCH-001, EDA-001 and SPLIT-001. Direct Python `run_local` also rechecks. Old RUNNING/VERIFIED local states, YAML labels, unsigned JSON and caller approval lists cannot satisfy this guard. `show`/`list` are descriptive, not authorization. Acquisition and legacy validators are unchanged; they are not research task-start entrypoints.

An external protected controller must authenticate tests, reviewer identities, approved business decisions and GitHub workflow/check producers, then issue an Ed25519-signed envelope. This implementation verifies signatures; it does not provide that controller, signing keys, automatic approval, key provisioning or GitHub branch protection. No trusted deployment is claimed. Without provisioning, the guard denies execution. An administrator must set `MOVIEREC_READINESS_PUBLIC_KEY_FILE` to an absolute PEM public-key path **outside** this checkout, protect that file and the runner environment from task authors, and keep the private key solely with the controller. Authors choosing their own key are not independent verification. The trust boundary excludes a malicious runner administrator or modified gate code.

`MOVIEREC_READINESS_BUNDLE_FILE` is a repository-relative POSIX path (default `.runtime/trusted-readiness.json`). Envelope: `{payload: <object>, signature: <base64>}`. Sign JSON serialized with `sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False` in UTF-8. Duplicate keys are rejected. Required payload:

| Field | Content |
|---|---|
| schema_version, repository, head_sha | 1, exact `git remote get-url origin`, exact current 40-character HEAD |
| issued_at, expires_at | Explicit UTC, issued ≤ now < expiry, validity at most 24 hours |
| dataset_manifest | `{path, sha256}` for the manifest below |
| inputs | Exact map of repository-relative prerequisite input paths to SHA-256; see binding rules below |
| tasks | Every transitive prerequisite keyed by ID: status VERIFIED, head_sha, dataset_manifest_sha256 |
| tasks[id].acceptance[AC-ID] | Contract test_case, nonempty command argument list, integer exit_code 0, report `{path, sha256}` |
| tasks[id].review | APPROVED, head_sha, distinct nonempty author_identity/reviewer_identity, report artifact |
| tasks[id].ci | repository, head_sha, scope `agent_contract` for infra or `product` otherwise; checks with name, id, started_at, head_sha, completed/success, app_slug `github-actions`, URL |
| decisions[ID] | APPROVED, head_sha, approved_by and report artifact for required ancestor/candidate decisions |

The protected controller must reject skipped/missing acceptance cases, confirm review covers this SHA, confirm approved decision scope, and select trusted workflows/apps using its protected allowlist. A local signature verifier does not turn arbitrary logs or a check name into trusted evidence. Policy requires `validate-contracts` for infra and `test` for product; contract-only CI cannot certify data/research. All artifact hashes are checked. Evidence is re-attested for each current HEAD and expires within 24 hours; cross-SHA reuse is unsupported in this version.

`readiness.required_inputs` computes the mandatory exact input inventory: all registered task contracts/index, gate/verifier scripts, quality policy, active workflow, each ancestor's committed acceptance test files, and all HEAD-tracked files matched by ancestor allowed_paths. Governance hashes are authenticated before the dependency graph selects other inputs; passed task objects must match those contracts. All hashes must match current bytes, and `git diff HEAD` must show those prerequisite files unchanged (Git normalizes platform line endings). Missing tests, uncommitted prerequisite artifacts, same-HEAD graph/AC/policy/source changes or extra/missing input hashes deny readiness. Broad ancestor allowlists conservatively include some shared documentation: editing a tracked predecessor input requires renewed upstream verification. New candidate files can be developed after start; overlapping predecessor inputs cannot silently change. Future granular artifact scopes can improve usability without weakening this boundary.

Manifest v1: `{schema_version: 1, raw_root: 'dataset_linkage_work/raw', files: [...]}`. Entries: repository-relative `path`, positive `size_bytes`, SHA-256, `source` (movielens/imdb/tmdb), nonempty `source_version`, `retrieved_at_utc`. Include six MovieLens/Genome CSVs, four IMDb dumps and three TMDb JSONLs. Keep manifest, bundle, full logs and license/coverage reports in ignored `.runtime/` or `dataset_linkage_work/`. Signed DATA-QUALITY-001 acceptance must additionally attest full row/schema/provenance/coverage/rights validation; hashes prove identity, not correctness. Source bytes are streamed without modification. Missing required sources deny readiness; optional enrichment may be absent only under an approved recorded coverage policy, never silently remove a required source.

## Future implementation constraints

EDA-001 will reuse `links.csv` normalization and source envelopes. Do not invoke acquisition, `migrate_v2`, `verify_dataset_linkage.main` (downloads/exports) or `verify_raw_data.verify` (writes a report) as read-only EDA shortcuts. Legacy header checks/crawl totals are insufficient readiness proof. Ratings are not ordered by timestamp; use external sorting or partitioned columnar reduction with UTC times and deterministic ties. Chunk CSV/TSV/JSONL; sparse user/movie counters are acceptable. Avoid dense user-item matrices, all-pairs user similarity and global quadratic interactions. Benchmark memory/wall time before selecting partitions.

After eligibility: ignored aggregate dataset/user/movie profiles, monthly/yearly first/last interaction and release timelines, cutoff comparison, cohort affinity/drift/sequence summaries, metadata/conflict/coverage audit, hypothesis evidence, report and aggregate-only dashboard. User-level exports remain restricted and untracked; publish approved aggregates with small-cell suppression. Stable sorting, pinned versions, seeds, UTC boundaries and hashes bind reports to one input manifest. Missing optional features yield coverage flags and narrower cohorts, never default zeros.

Signature implementation reference: [cryptography Ed25519 verification](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
