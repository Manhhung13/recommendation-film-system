# Repository instructions - MovieRec

Owner decision D-SDLC-2026-10-31 replaces prior mandatory external trust, independent
review and CI approval gates. Follow docs/agent/DEVELOPMENT_SDLC.md and the nested
kit instructions. Read task contracts, registry, slides and business decisions.

Workflow: ELIGIBLE -> IMPLEMENT -> TEST -> COMMIT -> PUSH -> DONE.
Dependencies require validated completion receipts, not YAML/local status. DONE
requires real passing tests, a scoped TASK-ID commit on feature/<name>, successful
push and remote SHA equal to local HEAD. CI is reported separately; no signatures
or mandatory independent review. Never relabel historical VERIFIED evidence.

Before edits inspect root/status/branch/HEAD/remotes and preserve all unrelated work.
Stage explicit paths only; inspect each staged file for secrets, datasets, generated
user exports, model artifacts and credentials. Run relevant tests, git diff --check
and git diff --cached --check. Commit and push each completed task, then use
agentctl complete/verify. Do not leave a completed changed-file task unpushed.
Never force push, bypass hooks/protection, auto-merge, or push directly to main.
On tests/push failure retain work and report the exact blocker; never mark DONE.

Never delete, recollect or mutate existing MovieLens/IMDb/TMDb raw data. Join movies
through links.csv; never infer cross-source user identity. Keep dataset integrity,
provenance, approved business decisions, dependency checks and leakage prevention.
Report TASK | STATUS | TESTS | BRANCH | COMMIT | PUSH | NEXT with evidence paths.
