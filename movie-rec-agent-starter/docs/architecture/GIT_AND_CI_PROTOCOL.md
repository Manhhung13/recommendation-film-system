# Git and CI protocol

Follow docs/agent/DEVELOPMENT_SDLC.md (owner decision D-SDLC-2026-10-31).
Tests -> scoped commit -> push -> confirm remote SHA -> DONE. CI is reported
separately for its exact SHA; never force push, auto-merge or commit raw/secrets.
