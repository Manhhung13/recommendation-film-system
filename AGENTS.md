# Repository instructions — Movie Recommendation System

These instructions apply at the Git repository root. The reference SDLC lives in `movie-rec-agent-starter/`; read its `AGENTS.md`, `PLANS.md`, relevant `tasks/<TASK-ID>.yaml`, business decisions, and quality gates before product work. The starter is a reference until integrated; its prompts and YAML do not themselves enforce CI or permissions. Explicit user instructions and approved business decisions take precedence over proposed defaults.

## Mandatory: auto commit and push after each changed-file task

For every task that changes repository files, complete the gates below, then **commit and push that task's eligible files to a feature branch** before reporting completion. This includes finished documentation and audit tasks. Do not silently leave a completed task only in the local worktree. A failed gate is not a completed task: report the blocker and retain the changes for correction. A separate, reviewed `BLOCKED` report may be committed if it contains no failing product code or sensitive data. Never use `git add -A` or stage an entire directory without inspecting its contents.

### Before editing

1. Confirm the actual root with `git rev-parse --show-toplevel`; inspect `git status --short`, `git branch --show-current`, and `git remote -v`. Record the starting HEAD and existing staged/unstaged/untracked files. Preserve all pre-existing user changes; never overwrite, reset, clean, remove, rename, or commit them as part of another task.
2. Identify the `TASK-ID`, task goal, allowed paths, linked slide requirements, dependencies, acceptance criteria, required checks, and tests. If no task registry entry exists, assign a clearly labeled local task ID for the handoff; do not pretend it is a registered or VERIFIED task. Resolve critical business decisions before dependent implementation.
3. Work on a `feature/<name>` branch. Create one before editing if on `main`; never push directly to `main`, force push, or bypass branch protection. Do not move unrelated user changes into the task commit.

### Before staging and committing

1. Inspect the exact changed-file list and diff. Run relevant tests and record commands, exit codes, and evidence. Run `git diff --check` and, after staging, `git diff --cached --check`. Never claim a test passed from source inspection alone.
2. Inspect each candidate file for secrets, `.env`, credentials, tokens, private data, large datasets, generated downloads, model artifacts, and checkpoints. Do not stage any of these. Do not alter quality gates, remove tests, or weaken checks to obtain a passing result. Preserve collected data in place.
3. Stage only explicit paths belonging to the task (`git add -- <path>...`). Review `git diff --cached --name-only`, `git diff --cached --stat`, and the staged diff before commit. If an unrelated file is staged, remove it from the index without discarding its worktree content.
4. A finished documentation/audit task may be committed after its content and links are checked. Commit coding only after required local tests and independent review pass. The author cannot approve their own independent review. If tests or review fail, correct within scope and rerun; do not commit failing product code as a completed task.
5. Use a commit message containing the `TASK-ID`, following repository style, for example `docs(sdlc): describe change [TASK-ID]`. Do not amend another commit, skip hooks/signing, or include unrelated files.

### Push, CI, and task state

1. Push the feature branch to `origin` (set upstream when publishing). Verify the remote branch and pushed commit SHA, and record the GitHub commit URL. A local commit alone is **not** a GitHub sync.
2. Check GitHub CI for the exact pushed SHA when checks exist. Use `CI_PENDING` while required checks have not finished, `CI_NOT_CONFIGURED` if the applicable product CI does not exist, and report actual failures. Contract-only CI does not certify product acceptance.
3. Set task status `VERIFIED` only when every required acceptance check, independent review, and required GitHub CI check for that exact SHA have passed. Otherwise report `NOT VERIFIED`, `BLOCKED`, or `NEEDS_REWORK` with evidence. Do not start a dependent task until its gates and business decisions are satisfied.
4. If push fails, report the precise error, preserve the local commit for retry, do not claim GitHub is synchronized, and do not mark the task VERIFIED. Never force push to overcome rejection.
5. Update the task report/handoff with actual status. Every final task summary must include: `TASK-ID`, files changed, tests passed/failed with commands and exit codes, commit SHA, branch, GitHub commit URL (or unavailable), push status, CI status, task status, and next eligible task (or none, with reason).

## Data and ML invariants

Keep MovieLens, TMDb, and IMDb raw sources and provenance intact; join movie metadata through `links.csv` IDs, never infer cross-dataset user identity. Do not run acquisition or remove collected data unless the task explicitly calls for it. Training/evaluation requires an approved temporal split without future leakage and measured baselines. Follow `movie-rec-agent-starter/.agents/policies/quality_gates.yaml` and the selected task's acceptance criteria; a YAML status or local assertion is not verification.
