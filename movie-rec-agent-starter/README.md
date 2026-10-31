# MovieRec development kit

Run from Git root. Read root/nested AGENTS.md, PLANS.md, task contracts and business
decisions. The active policy is docs/agent/DEVELOPMENT_SDLC.md, approved by the owner
as D-SDLC-2026-10-31. Existing raw datasets and product work are preserved.

Use agentctl validate/next/start/run-local/complete/verify and git_preflight.
ELIGIBLE -> IMPLEMENT -> TEST -> COMMIT -> PUSH -> DONE. Every completion needs
passing real tests, scoped TASK-ID commit and successful push confirmed by remote
SHA. Local YAML/state alone is insufficient. CI and optional review are separate.
No external key, signing controller or bootstrap approval is required.

agent-contracts CI validates the registry/harness only. Product CI is reported
separately; never claim product/data acceptance from contract-only CI. Roles and
tool YAML are project prompts/contracts, not native agents or permission grants.
