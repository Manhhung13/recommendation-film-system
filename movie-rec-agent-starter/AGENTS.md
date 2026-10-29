# Repository Instructions — Movie Recommendation + Agentic SDLC

This kit is integrated into the Git repository root but remains organized under `movie-rec-agent-starter/`. Run commands from the Git root. User-provided slide requirements have priority over proposed defaults. Start by reading `movie-rec-agent-starter/docs/business/SLIDE_REQUIREMENTS.md`, `movie-rec-agent-starter/docs/business/DECISIONS_TO_APPROVE.md`, this file, `movie-rec-agent-starter/PLANS.md`, and the selected task under `movie-rec-agent-starter/tasks/`.

## Working rules

1. One task at a time unless independent worktrees and explicit orchestration approve parallelism.
2. Find existing code, data contracts and tests before introducing new modules. Do not duplicate implementation.
3. For every task: restate its goal, linked slide numbers, dependencies, business invariants, acceptance criteria and planned tests.
4. Do not assume missing domain decisions: record ambiguities in `docs/business/DECISIONS_TO_APPROVE.md`; block the affected task if critical.
5. Make the smallest reviewable change in allowed paths. No unrelated cleanup, force push, secrets, production database edits or silent migration.
6. First implement testable behavior, then run the tests. Never claim success without actual command exit codes and recorded logs.
7. ML tasks must compare against explicit baselines on a leakage-safe temporal split; use real metric outputs, never guessed thresholds/results.
8. Independent reviewer must not be the same author and cannot approve by self-assertion. Branch protection/required CI remain external controls.
9. Commit after local checks + independent review; push feature branch; only treat task VERIFIED after GitHub CI for the exact SHA passes.
10. If gate fails: record evidence, correct within scope, rerun. If repeated or unsafe: mark BLOCKED and request human decision.

## Read on demand

- Business contracts: `movie-rec-agent-starter/docs/business/SLIDE_REQUIREMENTS.md` and `movie-rec-agent-starter/docs/business/DECISIONS_TO_APPROVE.md`.
- Architecture: `movie-rec-agent-starter/docs/architecture/PRODUCT_ARCHITECTURE.md` and `movie-rec-agent-starter/docs/architecture/AGENT_ARCHITECTURE.md`.
- Role: `movie-rec-agent-starter/.agents/roles/<role>.md`.
- Workflow and gate: `movie-rec-agent-starter/.agents/workflows/task_sdlc.yaml`, `movie-rec-agent-starter/.agents/policies/quality_gates.yaml`.
- Task definition: `movie-rec-agent-starter/tasks/<TASK-ID>.yaml`.
- Test mapping: `movie-rec-agent-starter/specs/ACCEPTANCE_TEST_CATALOG.md`.

## State reporting

In each Codex task completion summary report: task_id, changed files, acceptance IDs, exact commands executed, exit codes, artifacts/logs, assumptions, issues, current git branch/SHA, and whether remote CI has actually been checked. State `NOT VERIFIED` if any mandatory proof is missing.

`.agents/` files are project contracts/prompts; they are NOT automatically recognized Codex role configurations or executable MCP tools. A separate runner is needed for policy enforcement and automation.
