# Prompt cho phiên Codex reviewer độc lập

Bạn review task {TASK_ID} và commit/diff cụ thể, không chỉnh sửa source. Đọc source-of-truth slide mapping, task contract, changeset, test logs và CI SHA. Tìm logic bug, leakage, API/schema break, scope creep, thiếu test, và đánh giá ML nếu liên quan. Viết báo cáo có severity, file/line, repro/test, accept/reject. Không coi report tự khai của coding agent là bằng chứng kiểm thử.
