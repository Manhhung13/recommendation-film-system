# Những điểm cần nhóm xác nhận trước khi Codex triển khai

Dưới đây là **câu hỏi thiết kế còn mở**, KHÔNG phải điều kiện được slide khẳng định.

| ID | Cần quyết định | Tác động | Đề xuất mặc định (chỉ sau khi duyệt) |
|---|---|---|---|
| D-01 | `đã xem` gồm phim có rating, tag, click, feedback hay watch event thực sự? | Hybrid filter/top-K | Với MovieLens 25M chỉ có tương tác được quan sát; ghi nhãn `interacted_filter`, không nhận vơ full watch history. |
| D-02 | UI demo dùng Streamlit hay React? | UI-001 | Streamlit MVP; giữ FastAPI contract tách biệt. |
| D-03 | Temporal split theo từng user hay toàn cục? xử lý user ít lịch sử? | SPLIT-001 | Thiết kế split theo timestamp và ràng buộc quan sát; freeze trước tuning. |
| D-04 | Relevance label cho Precision@K/Recall@K/NDCG@K thế nào? | EVAL-001 | Rating ≥ ngưỡng được duyệt, chỉ trên interactions hợp lệ trong test. |
| D-05 | Ngưỡng chấp nhận metric/latency có số liệu baseline nào? | Release gate | Đặt baseline thực nghiệm trước; không điền số ảo. |
| D-06 | Muốn kiến trúc local/demo hay production-scale? | PostgreSQL/Redis/FAISS | MVP monolith offline + FastAPI; cache/index tùy benchmark. |
| D-07 | Làm SASRec thật ở giai đoạn đầu hay nâng cao? | SEQ-001 | Đánh dấu advanced/optional đến khi dữ liệu và metric baseline ổn. |
| D-08 | Bổ sung dữ liệu IMDb/TMDb bằng dump/API nào, chính sách rate-limit và điều khoản sử dụng? | DATA-004/005 | Chỉ ingest dữ liệu được phép; có retry, quota và source provenance. |
| D-09 | Định nghĩa warm/cold-start user/item và fallback khi thiếu dữ liệu? | BASE/CONTENT/HYBRID | Viết test riêng, tách new user/new item. |
| D-10 | Cần lưu & sử dụng feedback online để train định kỳ ra sao? | API-002/OPS | Có event schema/version, event timestamp và lịch retrain rõ ràng. |

**Nguyên tắc xử lý:** Task liên quan quyết định chưa duyệt phải bị `BLOCKED` nếu sự thiếu rõ ràng khiến acceptance criteria không kiểm chứng được. Không tự thay thế nội dung slide bằng mặc định của agent.
