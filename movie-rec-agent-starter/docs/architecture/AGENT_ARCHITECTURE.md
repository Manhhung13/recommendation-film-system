# Development orchestration

agentctl enforces dependencies, business decisions, real tests and Git/test receipts.
ELIGIBLE -> IMPLEMENT -> TEST -> COMMIT -> PUSH -> DONE. State is a local cache;
completion receipts are revalidated against logs, Git history and the remote.
No external trust controller or mandatory independent review/CI blocker.
See docs/agent/DEVELOPMENT_SDLC.md for owner decision D-SDLC-2026-10-31 and limits.
