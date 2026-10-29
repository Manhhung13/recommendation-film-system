# Implementation Plan — dependencies drive order

**Objective from slide 2:** personalized, unseen/interacted-filtered Top-K movies using rating/interaction sequence and movie content. Slides 3–11 describe MovieLens++ enrichment, baselines, hybrid ranking, offline/online service and evaluation.

**Milestone 0 — Agent foundations:** SETUP-001. Bootstrap Codex rules, reproducible CI, task registry and minimal verifier. Check scripts run before developing products.

**Milestone 1 — Data integrity:** DATA-001 → DATA-002, DATA-003, DATA-004, DATA-005 → DATA-006 → SPLIT-001. Preserve raw source, movie ID mappings and temporal boundaries.

**Milestone 2 — Baselines:** BASE-001, CF-001, CF-002, MF-001, CONTENT-001, KNOW-001, SEQ-001. Sequence/SASRec can be postponed to an advanced milestone; never falsely report it implemented.

**Milestone 3 — Hybrid:** HYBRID-001 candidate union/filter → HYBRID-002 ranking/diversity/MMR; EVAL-001 systematic evaluation & baselines.

**Milestone 4 — Product:** API-001 (`/recommend`, `/similar`), API-002 (`/feedback`), UI-001 (Streamlit or React, pending decision), OPS-001 (optional Redis/FAISS as appropriate), OPS-002 (telemetry), E2E-001.

Every task must pass business acceptance, local verification, review, Git commit/push and external CI **before** next dependent task is unblocked. A product task is not DONE just because markdown/YAML files exist.
