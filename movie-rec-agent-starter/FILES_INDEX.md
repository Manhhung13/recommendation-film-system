# Danh mục file mẫu — MovieRec Agentic SDLC

## Nên mở theo thứ tự

1. `README.md`: cách sử dụng và giới hạn của starter kit.
2. `AGENTS.md`: hướng dẫn Codex khi mở repository.
3. `docs/business/SLIDE_REQUIREMENTS.md`: mapping nghiệp vụ với 11 slide gốc.
4. `docs/business/DECISIONS_TO_APPROVE.md`: những nghiệp vụ còn cần xác nhận.
5. `docs/architecture/AGENT_ARCHITECTURE.md`: kiến trúc agent, state, quality gate, GitHub.
6. `.agents/prompts/START_HERE.md`: prompt giao cho Codex.
7. `.agents/roles/developer.md`, `.agents/roles/ml-evaluator.md`: ví dụ vai trò.
8. `.agents/tools/test-runner.yaml`, `.agents/tools/github-ci-reader.yaml`: ví dụ tool contracts.
9. `tasks/HYBRID-001.yaml`: ví dụ task hybrid có 3 AC/test cases.
10. `.agents/workflows/task_sdlc.yaml`: trạng thái và điều kiện chuyển bước.
11. `scripts/agentctl.py`: validator, dependency resolver, local test runner.
12. `scripts/github_ci.py`: đọc check-runs GitHub theo commit SHA.
13. `scripts/git_preflight.py`: kiểm tra thay đổi đúng phạm vi trước commit.

## Danh mục nghiệp vụ mẫu

- SETUP-001: Nền tảng agent/CI.
- DATA-001..DATA-006: MovieLens 25M, links.csv, Tag Genome, TMDb, IMDb, Feature Store.
- SPLIT-001: Temporal split chống leakage.
- BASE-001, CF-001/002, MF-001: Popularity, User-CF, Item-CF, SVD.
- CONTENT-001, KNOW-001, SEQ-001: Content, Knowledge, SASRec.
- HYBRID-001/002: Candidate union/filter, weighted rank + diversity/MMR.
- EVAL-001: RMSE/MAE, Precision@K, Recall@K, NDCG@K, Coverage, Diversity, Novelty.
- API-001/002, UI-001: Recommend, similar, feedback, web UI.
- OPS-001/002, E2E-001: Cache/index, monitoring, kiểm thử toàn tuyến.

**Chỉ số đúng:** bản kit có 24 task YAML; tất cả được đánh dấu `PLANNED`, không có code recommender được ngầm xác nhận là đã viết.
