# Research planning and readiness handoff

**Local TASK-ID:** SDLC-RESEARCH-PLAN-001, not a registered product task.
**Scope:** authorized planning/governance only, slides 2–6, 8, 11.
**Starting HEAD:** 079630c9431807fe0c39fdec7d7e5f8be125507c.
**Starting branch:** feature/sdlc-auto-commit-push.
**Working branch:** feature/research-readiness-governance.
**Origin:** https://github.com/Manhhung13/recommendation-film-system.git.

Pre-existing untracked `movie-rec-agent-starter/docs/agent/CURRENT_STATE_AUDIT.md` and `GAP_ANALYSIS.md` were preserved and excluded. There were no starting staged/unstaged tracked changes. No raw data, checkpoints, acquisition scripts, product validators, quality gates or business approvals are changed.

## Delivered scope and status

- Registered DATA-QUALITY-001 (all DATA-001..006), RESEARCH-001 (DATA-QUALITY-001) and EDA-001 (RESEARCH-001), all BLOCKED. SPLIT-001 depends on both DATA-006 and EDA-001. Index and contracts must agree; graph validation rejects cycles.
- Added a read-only signed-evidence verifier and guarded `next`, `start`, CLI/direct `run_local`, including resumed RUNNING states. It requires current-SHA trusted tests, independent review, appropriate product CI, approved decisions and the same stream-hashed dataset manifest across all ancestors. Local labels do not authorize these tasks.
- Added seven planning deliverables under `docs/research/`: framework, dictionary, H01–H12 registry, point-in-time feature catalog, temporal protocol, experiment design and bias/leakage risks. Every hypothesis has H0/H1, sources, formulas, features, cohorts, confounders, tests, metrics, uncertainty, potential algorithms, empty evidence and UNTESTED status.
- Added synthetic governance/contract tests. Semantic row validation, empirical EDA, temporal feature algorithms, dashboard, cutoff comparison and model experiments remain deferred acceptance work; they were not executed.

## Actual data inventory

Observed file presence/sizes and headers only, plus one TMDb envelope's keys per JSONL. All six MovieLens/Genome CSVs and README exist under `dataset_linkage_work/raw/movielens/ml-25m/`; MovieLens ZIP exists under `_archives/`. IMDb has title.basics, title.crew, title.principals and name.basics gzip dumps. TMDb has movie_details, keywords and credits JSONLs, checkpoint/crawl report and two staging JSON files. There is no verified manifest or validated coverage claim. IMDb title.ratings/akas/episode were not found in that inventory. No user rows were exported or raw data modified.

Existing `verify_raw_data.py` primarily checks headers/selected ID and crawl consistency and writes a report; its `database_design_can_start` flag is not this comprehensive readiness gate. The linkage sample entrypoint can download/export; it was not executed. Acquisition remains untouched. A source dictionary documents expected semantics from official GroupLens/IMDb/TMDb definitions and explicitly marks quality/coverage unmeasured.

## Changed files / implementation scope

18 eligible files: this report; seven `docs/research/` deliverables; kit `PLANS.md`, `requirements-agent.txt`, `scripts/agentctl.py`, new `scripts/readiness.py`, `tasks/index.yaml`, `tasks/SPLIT-001.yaml`, three new task contracts, and `tests/harness/test_research_readiness.py`. The active workflow and quality gates were not modified: existing CI already discovers the new unittest harness. `cryptography>=43` supports signature verification using the library implementation; no signing/private-key facility is shipped.

## Verification record (real commands)

Commands run from root, using `.venv-sdlc/Scripts/python.exe -X utf8 -B` (abbreviated `PY` below):

| Check | Exact command after PY | Exit / evidence |
|---|---|---|
| Registry/dependency consistency | `movie-rec-agent-starter/scripts/agentctl.py validate` | 0; 28 contracts, no cycles |
| Final existing + new regression suite | `-m pytest -q -p no:cacheprovider tests/harness movie-rec-agent-starter/tests/harness test_v3_pipeline.py` | 0; 48 passed, 41 subtests passed |
| Actual CI harness command | `-m unittest discover -s movie-rec-agent-starter/tests/harness -v` | 0; 37 tests, OK |
| Focused readiness after review fix | `-m pytest -q -p no:cacheprovider movie-rec-agent-starter/tests/harness/test_research_readiness.py` | 0; 26 passed, 41 subtests |
| Eligible task inspection | `movie-rec-agent-starter/scripts/agentctl.py next` | 0; no eligible tasks |
| Real premature start rejection | `movie-rec-agent-starter/scripts/agentctl.py start RESEARCH-001` | 2; trusted readiness public key not configured; explicit PowerShell `exit $LASTEXITCODE` preserves Python status |
| Whitespace | `git diff --check` (without PY) | 0; line-ending notices only |

Initial broad run failed (exit 1, 43 passed) because the existing live-data regression could not write `dataset_linkage_work/raw_data_report.json` under sandbox permissions. The authorized escalated rerun passed (44 tests before the review fix); the final run above passed 48. That **existing** regression calls the legacy validator, reads raw metadata/IDs and refreshes only its ignored generated report outside `raw/`. It is not new comprehensive QA/EDA execution or source mutation. No raw files/checkpoints were edited. Dependency installation first failed on sandbox socket permissions (exit 1), then succeeded after approved escalation (exit 0); no dependency requirement was weakened.

Tests cover signature/anchor failures, all transitive evidence, expired/future/non-UTC/malformed timestamps, missing/changed sources and artifacts, source manifest shape, duplicate JSON keys, bad hashes/traversal, pending/failed/stale/contract-only product CI, independent review identity, missing decisions and all guarded entrypoints before writes. Additional regression tests reject same-HEAD index/contract/policy/source drift, in-memory acceptance removal, unsigned input inventories and uncommitted acceptance tests. Protocol tests check twelve-hypothesis completeness, point-in-time/missing/shrinkage definitions and resolvable links. These are governance tests, **not** tests of implemented sparse-user/release-cutoff/temporal EDA algorithms; those future acceptance files remain absent and fail closed.

## Independent review

Reviewer `/root/independent_review` is separate from the author. Initial decision NEEDS_REWORK found a same-HEAD mutable-contract replay: removing dependencies could bypass unsigned graph selection. Fixed by authenticating governance hashes before graph traversal, exact signed input inventory, task-object equality, committed prerequisite test/source bindings and a clean-against-HEAD prerequisite check. Reviewer retested the fix: **PASS**, no blocking findings; independent harness pytest exit 0 (42 passed, 41 subtests), validate exit 0 and diff check exit 0.

Reviewed 17 code/planning files (excluding this evolving handoff report). Scope digest `b5be1c90c6d9417365a25c2d3266d420584d4034bf50b1018fc319d9deab3791` = SHA256 of canonical JSON `{sorted path: SHA256(raw bytes)}` with sorted keys and compact separators. This is scoped independent code review, not trusted-controller provisioning or product acceptance.

## Publication and task state

This tracked report is a pre-publication snapshot: local governance checks/review passed; task state **NOT VERIFIED** as a registered product task. Exact pushed SHA, GitHub commit URL, push outcome, staged checks and exact-SHA hosted CI observation are recorded in the final handoff and ignored `.runtime/evidence/SDLC-RESEARCH-PLAN-001/publication.json` after publication. A report cannot embed the hash of its own resulting commit. Until that evidence exists, publication/remote CI must be treated as pending, never inferred from local tests. The three registered future tasks remain BLOCKED regardless of contract CI.

## Blockers and next work

Runtime currently records only integration LOCAL_VERIFIED; DATA-001..006, new research tasks and their required empirical test files are not VERIFIED. D-03, D-04, D-08 and D-09 are open; D-01 applies to later filtering. A protected external signing controller/key, trusted approval/test provenance and applicable product CI are not provisioned. The verifier fails closed without them. Contract-only hosted CI cannot certify product research acceptance. No model training is authorized by these tasks.

No dependent product/research task is eligible on current evidence. Resume verification of SDLC-INTEGRATION-001, then SETUP-001; SETUP-001 cannot start until its dependency is VERIFIED. Registering planning drafts does not waive this order.
