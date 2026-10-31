# SETUP-001 - development harness and CI

Slides 2, 10, 11. Depends on the validated SDLC-INTEGRATION-001 completion receipt.
Owner policy D-SDLC-2026-10-31 remains in force; no external key/review/CI blocker.
This task reuses agentctl tests, completion receipts, dependency/decision checks,
manifest integrity and Git preflight. No acquisition or raw source access is needed.

## Reproduce from repository root (Windows PowerShell)

Existing local environment: Python 3.13.12. GitHub CI targets Python 3.12; report
its actual result separately.

```powershell
# Use the existing .venv-sdlc; a new checkout may create it with py -3.12 -m venv .venv-sdlc.
.\.venv-sdlc\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/agentctl.py validate
.\.venv-sdlc\Scripts\python.exe -X utf8 -B -m pytest -q
```

pytest.ini supplies test discovery, script imports and strict marker registration.
The pinned file contains only the test environment, including transitive pytest
dependencies. It does not pin future recommender/runtime/ML requirements.

SETUP-001-AC-01 checks graph/policies and a genuinely invalid dependency graph.
AC-02 checks executable workflow commands, pinned dependencies, discovery paths,
least-privilege CI and separate contract/product scope. AC-03 executes the CLI
validator/help and validates the documented publication protocol. The existing
harness executes real synthetic Git remotes/processes to test failed tests, missing
push, mismatched SHA, changed evidence, forged status and unrelated-work preservation.

agent-contracts runs the registry validator, unittest harness and integration checks.
movie-rec-product runs all root tests currently present; at setup these are harness
acceptance tests. It does not claim implemented recommender/data/model acceptance.
Both use requirements-test.txt on Python 3.12; neither downloads raw datasets or
requires keys/credentials. CI status is reported separately for each actual SHA.

## Publish and verify

Follow docs/agent/DEVELOPMENT_SDLC.md: feature branch, explicit staging, run-local,
git_preflight, inspect diff, scoped [SETUP-001] commit, push, complete and verify.
complete re-runs the tests at committed HEAD, checks remote SHA equality and records
ignored .runtime/evidence/SETUP-001/completion.json with changed files and log hashes.
verify independently rechecks recorded evidence and remote Git ancestry. No state
migration from historical VERIFIED is performed. Stop after SETUP-001; DATA-001 is
for the next prompt. Open product business decisions remain unapproved.
