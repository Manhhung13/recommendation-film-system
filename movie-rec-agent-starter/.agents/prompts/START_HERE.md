# Prompt sao chép vào Codex

Hãy đóng vai SDLC Orchestrator cho project MovieRec. Làm việc từ Git repository root. Trước khi code, đọc `AGENTS.md`, `movie-rec-agent-starter/AGENTS.md`, `movie-rec-agent-starter/PLANS.md`, `movie-rec-agent-starter/docs/business/SLIDE_REQUIREMENTS.md`, `movie-rec-agent-starter/docs/business/DECISIONS_TO_APPROVE.md`, `movie-rec-agent-starter/.agents/workflows/task_sdlc.yaml`, `movie-rec-agent-starter/.agents/policies/quality_gates.yaml` và task dưới `movie-rec-agent-starter/tasks/`.

1) Chỉ thực hiện SETUP-001 (không làm task chưa đủ dependencies). 2) Kiểm tra codebase hiện tại và lập plan. 3) Triển khai chức năng đúng file scope. 4) Viết test theo acceptance IDs và chạy test thật. 5) Không tự nhận QA/review/CI pass; xuất báo cáo test thật với exit codes và file diff. 6) Đề xuất commit với thông điệp gồm task ID nhưng KHÔNG tự push/merge nếu chưa được cấp quyền cụ thể.

Sau khi xong hãy trả bảng: AC-ID | Test | Command | Exit code | Evidence | Status và đề xuất task kế tiếp dựa trên dependencies. Nếu thiếu nghiệp vụ hoặc dataset, dừng ở BLOCKED và ghi rõ quyết định cần duyệt.
