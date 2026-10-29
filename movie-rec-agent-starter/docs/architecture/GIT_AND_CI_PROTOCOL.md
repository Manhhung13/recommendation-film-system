# Git & CI protocol — đề xuất thực hiện

1. Per feature: tạo nhánh `feature/<feature-name>`; mỗi task có commit `feat(scope): description [TASK-ID]` sau local tests + review pass.
2. Quyền: Coding agent không được force push, đổi protected branches hoặc sửa secret; Git Controller chạy trong runtime được cấp quyền riêng. Prefer GitHub App installation token, giữ token ở secret store; không lưu vào repo.
3. **Không commit code nếu chỉ có báo cáo tự khai**. Test process exit code và log gốc phải được runner ghi lại. Chặn commit nếu changed files nằm ngoài allowlist task.
4. Sau push: GitHub Actions chạy `product-ci` trên commit SHA; monitor phải kiểm tra required checks thực tế của đúng SHA. Chỉ sau đó mới lưu `VERIFIED`.
5. Khi CI fail: task `NEEDS_REWORK`, sửa và commit mới; không thay thế lịch sử bằng force push. Nếu có sự cố giữa push và ghi state, reconcile bằng SHA/task ID.
6. Chỉ merge PR sau required checks + review, theo branch protection. Có thể commit nhiều task trước khi merge feature.
7. Repo có CI contract scaffold (`.github/workflows/agent-contracts.yml`) và CI sản phẩm dạng template (`templates/movie-rec-product-ci.yml.template`). Contract CI pass không đồng nghĩa product CI pass.

**Lưu ý chính thức của GitHub:** `GITHUB_TOKEN` trong một Actions workflow dùng để push không tự kích hoạt `push` workflows mới (trừ một số ngoại lệ cụ thể). Xem https://docs.github.com/en/actions/concepts/security/github_token

**ChatGPT analysis:** GPT/GitHub connector có thể đọc repo và đánh giá code/diff/checks khi người dùng yêu cầu. Nó không phải một luôn-on auditor chỉ bằng việc connect repository; auto-trigger cần GitHub App/Webhook và scheduler riêng.
