# Thiết kế Agentic SDLC — giải pháp đề xuất (không nằm trong slide)

```
User → Task Registry → Orchestrator/Planner → Analyst/Architect → Coder (worktree)
                                             ↓
                                       Local test runner
                                             ↓
                                   QA + ML Evaluator + Reviewer
                                             ↓
                                    Quality Gate (trusted)
                                             ↓
                                      Git commit → push
                                             ↓
                                      GitHub Actions
                                             ↓
                                 CI evidence for exact SHA
                                             ↓
                                   State VERIFIED → Next task
```

**Điểm cứng:** Agent không được tự cấp trạng thái PASSED. Bằng chứng test phải được ghi từ process thực, review từ reviewer độc lập, remote CI từ GitHub API/Webhook có xác thực. GitHub `main` dùng PR & branch protection; mỗi task có commit trên feature branch, không tự merge sau từng task.

**State machine đề xuất:** `PLANNED → READY → RUNNING → LOCAL_VERIFIED → REVIEW_APPROVED → COMMITTED → CI_PENDING → VERIFIED`. Fail/retry: `NEEDS_REWORK`, `BLOCKED`. Lưu state ở PostgreSQL trong phiên bản production; `.runtime/state.json` trong kit chỉ là bản demo local, không chịu được multi-worker hoặc crash giữa các giao dịch.

**Boundaries:** Codex có thể đọc AGENTS.md và file role, nhưng role YAML/Markdown không tạo process agent tự động. Muốn chạy nhiều vai trò cần Orchestrator thực sự, sandbox per worker, tool gateway và permissions enforce ở tầng runtime.

**Evidence identity:** local check bind theo working-tree revision/diff digest; commit bind theo SHA; remote CI cần `head_sha` và required check names. Webhook phải kiểm tra signature, chống replay và idempotent trước khi áp dụng state transition. Bản mẫu không tự cài đặt đầy đủ kiểm tra này.

**Sử dụng với Codex ngay:** yêu cầu Codex đọc `AGENTS.md`, `.agents/roles/developer.md` và task; làm plan nhỏ; code+test; báo lại commands, exit status và diff. Review độc lập ở vòng tương tác khác. Khi đội đã tin tưởng, mới xây controller tự vận hành.
