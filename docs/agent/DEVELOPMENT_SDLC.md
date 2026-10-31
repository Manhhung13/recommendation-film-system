# Owner-approved development SDLC (2026-10-31)

Decision D-SDLC-2026-10-31: the repository owner explicitly replaced the external
trust/bootstrap workflow with ELIGIBLE -> IMPLEMENT -> TEST -> COMMIT -> PUSH -> DONE.
This decision removes mandatory independent review, signatures, bootstrap approval,
and product CI as task blockers. It does not approve open product/business decisions.
Historical LOCAL_VERIFIED/VERIFIED records are preserved; none are converted to DONE.

## Completion protocol

Read the task, slides, approved decisions, allowed paths and dependency graph. Work
sequentially on feature/<name>. Preserve unrelated staged, unstaged and untracked
work. Never acquire, overwrite, delete, or commit existing raw datasets.

Run relevant automated tests, inspect diff and staged content for secrets/artifacts,
and stage explicit task paths only. Never git add -A, force-push, amend another
commit, bypass hooks, push directly to main or automatically merge.

From the repository root (PowerShell; use the existing .venv-sdlc Python):

```powershell
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/agentctl.py validate
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/agentctl.py next
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/agentctl.py start TASK-ID
# Implement; stage explicit paths; run-local requires no unstaged tracked changes.
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/agentctl.py run-local TASK-ID
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/git_preflight.py TASK-ID
git diff --check
git diff --cached --check
# Inspect git diff --cached, including secret and artifact checks.
git commit -m "feat(scope): description [TASK-ID]"
git push -u origin HEAD
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/agentctl.py complete TASK-ID
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/agentctl.py verify TASK-ID
```

`complete` re-runs the registered tests at clean committed HEAD, checks task-scoped
commit paths and TASK-ID, and confirms origin feature ref equals local HEAD before
and after tests. Failure cannot create DONE. Evidence/logs remain ignored under
.runtime/evidence/<TASK-ID>/. Receipts bind tests to the committed tree and hashes.
`verify` and dependency checks validate receipts, logs, Git ancestry and live remote
containment. YAML/status alone never authorizes downstream work. These are local
audit records, not authenticated signatures or a malicious-user security boundary.
On a new checkout, restore evidence or re-run completion at its original commit;
do not invent receipts. Business decisions remain explicit owner records.

CI is reported separately for its actual SHA: NOT_CHECKED, CI_PENDING,
CI_NOT_CONFIGURED, PASSED or FAILED. Contract CI does not certify product/data
acceptance. A CI result is never fabricated or required for DONE by this policy.
Review remains optional. DATA-QUALITY produces a hashed manifest; research/EDA/split
validate all required raw sources, sizes, versions and timestamps against it before
execution. Preserve temporal ordering, source provenance and links.csv identities.

Each checkpoint reports TASK | STATUS | TESTS | BRANCH | COMMIT | PUSH | NEXT, plus
changed files and evidence paths. Stop at failed tests, Git failures or essential
unresolved dependencies/decisions. This session stops after SETUP-001.
