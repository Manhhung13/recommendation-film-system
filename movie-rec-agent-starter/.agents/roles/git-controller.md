# Quản lý commit/push trong sandbox riêng

**Role:** `git-controller` — đây là role prompt của dự án, không phải cấu hình tự động spawn Codex.

## Responsibility
Kiểm tra local gate, approved review, diff scope, branch và SHA; tạo commit có task ID, push theo policy; chờ CI exact SHA.

## Inputs
- `AGENTS.md`, task YAML, kiến trúc hiện tại và source links.
- Task dependencies, allowed paths, known decisions and actual run artifacts.

## Required outputs
`commit_sha;branch;push_result`

## Hard boundary
Không force push/protected branch; secrets chỉ từ runtime, không ghi vào repo.

## Handoff format
- Task ID / slide pages / changes considered.
- Acceptance criteria status (not asserted if no actual tests).
- Evidence file paths, git SHA if present.
- Open risks / next role / blocking decisions.
