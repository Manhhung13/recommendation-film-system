# MovieRec Agentic SDLC — integrated repository kit

> Kit được tích hợp trong `movie-rec-agent-starter/` và được quản lý từ Git root. Roles, tool contracts, workflows, tasks và policies là cấu hình/prompt dự án; YAML không tự tạo native agent, quyền tool, review độc lập hoặc publisher an toàn. Chưa có recommendation code hay business acceptance tests.

## Bắt đầu trong 5 phút

1. Làm việc tại Git root và đọc `AGENTS.md`, `movie-rec-agent-starter/AGENTS.md`, business contracts và task liên quan.
2. Cài phụ thuộc: `python -m pip install -r movie-rec-agent-starter/requirements-agent.txt`.
3. Kiểm tra task contracts và dependency graph: `python movie-rec-agent-starter/scripts/agentctl.py validate`.
4. Xem task sẵn sàng: `python movie-rec-agent-starter/scripts/agentctl.py next`; xem chi tiết: `python movie-rec-agent-starter/scripts/agentctl.py show SETUP-001`.
5. Dùng prompt `movie-rec-agent-starter/.agents/prompts/START_HERE.md` và đọc task contract trước khi sửa code.
6. Chạy task: `python movie-rec-agent-starter/scripts/agentctl.py start TASK-ID`, rồi `python movie-rec-agent-starter/scripts/agentctl.py run-local TASK-ID`. Runner fail-closed nếu test khai báo thiếu hoặc chạy lỗi. Chạy `python movie-rec-agent-starter/scripts/git_preflight.py TASK-ID` để kiểm tra branch và allowlist (không commit/push).
8. Quy trình GitHub mong muốn: local checks pass → review độc lập → commit trên feature branch → push → CI đúng SHA → trạng thái VERIFIED → task tiếp theo. Những bước kết nối Github/duyệt review/chuyển trạng thái tự động **chưa được tự động hóa toàn diện** trong bộ mẫu.

## File nào hoạt động với Codex?

| Nhóm file | Mức hỗ trợ |
|---|---|
| `movie-rec-agent-starter/AGENTS.md` | Hướng dẫn kit bổ sung cho root `AGENTS.md`. |
| `movie-rec-agent-starter/.agents/skills/movie-rec-task/SKILL.md` | Skill dự án; discovery phụ thuộc runtime Codex. |
| `movie-rec-agent-starter/.agents/roles/*.md` | Prompt vai trò; không tự sinh native agents. |
| `movie-rec-agent-starter/.agents/tools/*.yaml` | Tool contracts; không tự cấp quyền hoặc gọi tool. |
| `movie-rec-agent-starter/.agents/workflows/*.yaml` | Workflow definitions; cần runner để tự thực thi transitions. |
| `movie-rec-agent-starter/tasks/*.yaml` | Task contracts; `agentctl.py` đọc/validate và chạy acceptance tests. |
| `movie-rec-agent-starter/scripts/` | Validator/state demo, preflight và GitHub check reader; không tự duyệt task hoặc push. |
| `.github/workflows/agent-contracts.yml` | CI thực thi task contract/harness; không chứng nhận product implementation. |
| `templates/movie-rec-product-ci.yml.template` | Mẫu CI sản phẩm; cần điều chỉnh và kích hoạt khi dự án có code. |

## Cấu trúc quan trọng

```
AGENTS.md                         ← Quy tắc repository + commit/push
.github/workflows/                ← CI task contracts/harness
movie-rec-agent-starter/.agents/  ← Roles, tool contracts, policies, workflows, prompts
movie-rec-agent-starter/tasks/    ← Task registry/dependency graph
movie-rec-agent-starter/scripts/  ← CLI, local state demo, preflight, CI reader
movie-rec-agent-starter/contracts/ ← API/data schemas mẫu
movie-rec-agent-starter/configs/  ← Candidate/evaluation config
movie-rec-agent-starter/specs/    ← Acceptance test catalog
movie-rec-agent-starter/tests/    ← Agent harness tests
movie-rec-agent-starter/src/      ← Product placeholder
```

## Nguyên tắc không được bỏ qua

- Không coi `status: PLANNED` là đã implement.
- Không cho phép `pytest` thiếu test mà vẫn xác nhận task hoàn thành.
- Không tự tạo số đo Precision@K, NDCG@K, RMSE, latency hoặc benchmark.
- Không trộn `userId` của MovieLens với user ở nguồn khác. ID liên kết phim là `links.csv`.
- Không coi rating MovieLens tương đương log đã **xem** đầy đủ; phải duyệt chính sách lọc interacted/watched.
- Không cho agent tự tuyên bố CI pass; CI phải truy từ GitHub theo commit SHA và ngữ cảnh xác thực.
- Không cho agent tùy ý sửa chính gate/policy để vượt gate; production phải dùng trusted runner có quyền tách biệt.

## Nguồn và ghi chú

Nguồn nghiệp vụ: tệp trình chiếu 11 trang do người dùng cung cấp. Xem trace ở `movie-rec-agent-starter/docs/business/SLIDE_REQUIREMENTS.md`.

Tham khảo Codex: https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex
GitHub Actions GITHUB_TOKEN: https://docs.github.com/en/actions/concepts/security/github_token
