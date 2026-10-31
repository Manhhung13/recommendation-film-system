# MovieRec kit instructions

The kit runs from Git root. Root AGENTS.md and docs/agent/DEVELOPMENT_SDLC.md define
the owner-approved development SDLC (D-SDLC-2026-10-31). Read PLANS.md, selected
contracts/tasks, business slide requirements and decisions, and quality_gates.yaml.

ELIGIBLE -> IMPLEMENT -> TEST -> COMMIT -> PUSH -> DONE. One task at a time. Reuse
existing code/tests/data. Implement acceptance behavior, run actual tests and record
exit codes. A dependency needs a validated test/Git completion receipt; local YAML
or historical VERIFIED bits do not suffice. No mandatory reviewer signatures,
bootstrap trust, independent review, or product CI gate. Optional reviews and CI
are reported honestly and separately. Owner-approved business decisions still apply.

Use exact allowed paths, stage explicitly, inspect content and both diff checks,
commit TASK-ID, push the feature branch, confirm remote SHA and run complete/verify.
Preserve unrelated work; never force push, auto-merge, commit secrets/artifacts or
change raw data. ML must use temporal splits and measured baselines. Missing tests,
failed tests/push or essential unresolved decisions block completion. Report actual
commands, exit codes, branch/SHA, changed files, evidence and next eligible task.
Roles/tool YAML are prompts/contracts, not native agents or tool permissions.
