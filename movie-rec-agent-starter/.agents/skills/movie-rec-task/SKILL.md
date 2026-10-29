---
name: movie-rec-task
# This is a project-local skill example; availability depends on Codex runtime setup.
description: Execute a single Movie Recommendation SDLC task with slide-linked acceptance, tests, review and verified GitHub evidence.
---

When assigned a MovieRec task:

1. Read `AGENTS.md`, `docs/business/SLIDE_REQUIREMENTS.md`, relevant `tasks/TASK-ID.yaml` and `docs/business/DECISIONS_TO_APPROVE.md`.
2. Confirm dependencies; never start blocked/unapproved tasks. Use `python scripts/agentctl.py validate` and `python scripts/agentctl.py next`.
3. Choose role from `.agents/roles/`, inspect repository before edits and write a narrow plan.
4. Implement only within task `allowed_paths`; test each AC and critical edge cases; run `python scripts/agentctl.py run-local TASK-ID` when product tests exist.
5. Provide actual command logs, exit codes, changed files, artifacts and open issues; arrange independent QA and review.
6. Commit/push only after authorized gate; remote GitHub CI must be verified for exact SHA. Never assert `VERIFIED` based on agent text.

Do not treat this SKILL file as a complete autonomous workflow engine.
