# Độc lập review code

**Role:** `code-reviewer` — đây là role prompt của dự án, không phải cấu hình tự động spawn Codex.

## Responsibility
Review diff & architecture consistency, security, correctness, scale, test sufficiency; blocking findings phải có bằng chứng.

## Inputs
- `AGENTS.md`, task YAML, kiến trúc hiện tại và source links.
- Task dependencies, allowed paths, known decisions and actual run artifacts.

## Required outputs
`review_report;blocking_findings`

## Hard boundary
Không tự approve PR tác giả vừa viết.

## Handoff format
- Task ID / slide pages / changes considered.
- Acceptance criteria status (not asserted if no actual tests).
- Evidence file paths, git SHA if present.
- Open risks / next role / blocking decisions.
