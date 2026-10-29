# SDLC kit integration report

**Task:** SDLC-INTEGRATION-001
**Repository root:** `E:/recommendation-film-system`
**Branch at integration:** `feature/sdlc-auto-commit-push`

## Summary

Integrated the existing kit under `movie-rec-agent-starter/` without relocating or duplicating its modules. The task CLI now resolves the real Git root for product paths and `.runtime` state while loading contracts from the nested registry. Root commands and CI entry points are documented. The active GitHub Actions workflow is at `.github/workflows/agent-contracts.yml`.

The original data acquisition/validation scripts, schemas, collected datasets, checkpoints, and source formats were not changed. The integration task is registered as the first eligible task; `SETUP-001` now depends on it.

## Files created or modified

- Created: `.github/workflows/agent-contracts.yml`, `docs/agent/SDLC_INTEGRATION_REPORT.md`, `tests/harness/test_integration_001.py`, `movie-rec-agent-starter/tasks/SDLC-INTEGRATION-001.yaml`.
- Modified: `.gitignore`, root `AGENTS.md`, nested kit `AGENTS.md` and `README.md`, root-relative prompt/tool command examples, `scripts/agentctl.py`, `scripts/git_preflight.py`, task registry and `SETUP-001` dependency, and the harness eligibility test.
- Preserved outside this task commit: the prior audit outputs `movie-rec-agent-starter/docs/agent/CURRENT_STATE_AUDIT.md` and `GAP_ANALYSIS.md`; these remain local and untracked.

## Verification evidence

| Check | Command | Result |
|---|---|---|
| Task contracts and dependency graph | `.venv-sdlc/Scripts/python.exe -B movie-rec-agent-starter/scripts/agentctl.py validate` | Exit 0 — 25 task contracts valid; no dependency cycles. |
| Existing harness | `.venv-sdlc/Scripts/python.exe -B -m unittest discover -s movie-rec-agent-starter/tests/harness -v` | Exit 0 — 11 tests passed. |
| Integration acceptance tests and workflow structure | `.venv-sdlc/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/harness/test_integration_001.py` | Exit 0 — 5 passed. Checks workflow triggers, permissions, runner, setup, ordered commands, and effective job check name. |
| Check-name regression cases | Same focused integration command | Exit 0 — renamed explicit job name is rejected by the shared helper; missing explicit name falls back to job ID `validate-contracts`. Product `test` remains separate. |
| Full Agent SDLC suite | `.venv-sdlc/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/harness movie-rec-agent-starter/tests/harness` | Exit 0 — 16 passed. |
| Task state/local runner | `.venv-sdlc/Scripts/python.exe -B movie-rec-agent-starter/scripts/agentctl.py start SDLC-INTEGRATION-001`; `.venv-sdlc/Scripts/python.exe -B movie-rec-agent-starter/scripts/agentctl.py run-local SDLC-INTEGRATION-001` | Both exit 0; task reached `LOCAL_VERIFIED`; runner explicitly reports no independent review, commit, push, or CI verification yet. Evidence is in ignored `.runtime/evidence/`. |
| Git preflight | `.venv-sdlc/Scripts/python.exe -B movie-rec-agent-starter/scripts/git_preflight.py SDLC-INTEGRATION-001` | Exit 0 — branch and changed paths passed allowlist. Preflight is not review approval. |
| Whitespace/diff | `git diff --check` | Exit 0 before the final report edit; only this report row changed afterward. Nothing was staged, so `git diff --cached --check` was not applicable. |

The first system-Python pytest attempt exited 1 because `pytest` was absent; `python -B -m unittest discover -s tests/harness -v` exited 5 because the root integration checks are pytest functions. Installed kit requirements into ignored `.venv-sdlc/`, then ran the successful commands above. No pipeline regression test was run because no pipeline source changed.

## Allowlist defect follow-up — SDLC-INTEGRATION-001

The independent review found that `check_allowed_paths` used unrestricted prefix matching for exact-file rules, allowing names such as `AGENTS.md.bak` under an `AGENTS.md` rule. The fix now treats rules ending in `/` as directory rules and all other rules as exact files. Candidate and rule separators are normalized to `/`; absolute POSIX and drive-rooted paths and any `..` path component are rejected before matching.

Regression coverage in `tests/harness/test_integration_001.py::test_sdlc_integration_001_allowlist_paths` accepts exact files, nested directory files, and backslash-separated nested paths. It rejects file suffixes, sibling directory prefixes, traversal, and POSIX/Windows absolute paths.

Verification from repository root using `.venv-sdlc/Scripts/python.exe`:

| Check | Command | Result |
|---|---|---|
| Contract validation | `.venv-sdlc/Scripts/python.exe -B movie-rec-agent-starter/scripts/agentctl.py validate` | Exit 0; 25 contracts, no cycles. |
| Agent harness | `.venv-sdlc/Scripts/python.exe -B -m unittest discover -s movie-rec-agent-starter/tests/harness -v` | Exit 0; 11 tests passed. |
| Root integration tests | `.venv-sdlc/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/harness/test_integration_001.py` | Exit 0; 5 passed. |
| Full Agent SDLC suite | `.venv-sdlc/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/harness movie-rec-agent-starter/tests/harness` | Exit 0; 16 passed. |
| Allowlist regression | `.venv-sdlc/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/harness/test_integration_001.py -k allowlist` | Exit 0; 1 passed. |
| Whitespace check | `git diff --check` | Exit 0; only pre-existing line-ending warnings. |

Acceptance covered: SDLC-INTEGRATION-001-AC-03. No Data Pipeline source, task registry, quality gates, or collected data changed. Remaining limitations: this check validates repository-relative strings and is not a security boundary for filesystem resolution or symlink targets; trusted review and exact-SHA hosted CI remain separate gates. Status remains NOT VERIFIED pending independent review and remote CI. No commit or push performed as instructed.

The prior root test only searched the parsed workflow for command strings. It now validates the workflow structure and ordered job steps that configure GitHub Actions to run the required commands. This resolves the local configuration-check gap; it does not prove a hosted Actions execution. Remote CI was not run or required before the first push, so exact-SHA GitHub CI remains pending.

CI check names are separated by scope: `agent_contract_ci_checks: [validate-contracts]` matches the active workflow job, while `product_ci_checks: [test]` preserves the product-level CI requirement. The GitHub CI reader examples show both names. The integration tests use a shared effective-name assertion helper; the negative test supplies `name: renamed-contract-check` in memory and confirms the helper rejects it, while the positive case confirms fallback to the job ID. These are local results; the hosted workflow still needs its post-push run.

## What works and what remains declarative

- **Executed successfully:** contract/index validation including cycle detection; dependency-based eligibility; local task state; named-test fail-closed runner; root-relative Git path preflight; CI check-reader unit tests; root workflow command configuration.
- **Configuration only:** specialist role prompts, tool contracts, and the YAML SDLC/data/model workflows. They do not spawn agents, grant tool permissions, or enforce independent review by themselves.
- **Runtime still required:** trusted Git publisher, independent-review enforcement, durable shared task-state service, automatic workflow transitions, and product implementation/acceptance tests. Root CI validates the agent harness only; it does not verify recommendation functionality.

## Status and next step

Local verification is `LOCAL_VERIFIED`; task status remains **NOT VERIFIED** until an independent review and required GitHub checks for the pushed SHA are confirmed. No commit or push was performed, as explicitly requested. Next task: `SETUP-001`, now dependent on this integration task. No product/data pipeline task was started.
