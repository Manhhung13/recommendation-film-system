# Đặc tả nghiệp vụ rút trực tiếp từ 11 slide do người dùng cung cấp

**Phạm vi trích:** Chỉ ghi các yêu cầu/đề xuất thể hiện trong slide. Những thứ thêm để tổ chức SDLC phải ghi riêng là *đề xuất kỹ thuật*.

| Trang | Nội dung gốc từ slide | Ảnh hưởng tới task |
|---|---|---|
| 2 | Ước lượng `score(user,movie)`, xếp hạng và trả Top-K phim chưa xem; rating/interaction, timestamp, genre, Tag Genome, TMDb/IMDb. | RECO, FILTER, API, EVAL |
| 3 | MovieLens++ = MovieLens 25M + Tag Genome + TMDb + IMDb. | DATA-001..DATA-006 |
| 4 | MovieLens có userId/movieId/rating/timestamp/genres/tags/links; Tag Genome `tagId`, `relevance`; TMDb overview/keywords/cast/crew; IMDb actor/director/writer/runtime/year. | Data contracts, validators |
| 5 | `ratings.csv` → User/Item-CF, SVD; timestamp → SASRec; movies.csv genres → content baseline; tags/Tag Genome → semantic features; TMDb/IMDb → content & knowledge constraints. | CF, MF, CONTENT, KNOW, SEQ |
| 6 | Join movie metadata theo `links.csv` `movieId ↔ tmdbId ↔ imdbId`; giữ raw sources, tránh leakage; feature store có genres/tags/tag genome vector/overview/keywords/director/actors/runtime/year. Không trộn user khác dataset. | DATA-002, DATA-006, SPLIT-001 |
| 7 | Baselines: Popularity, User-CF, Item-CF, SVD. | BASE-001, CF-001/002, MF-001 |
| 8 | Content-Based: TF-IDF hoặc embeddings và cosine; Knowledge-Based: runtime/year/actor/director/genres; Sequential/SASRec từ lịch sử theo timestamp. | CONTENT-001, KNOW-001, SEQ-001 |
| 9 | Hybrid: SVD=100, Content=100, Knowledge=50, Popular=30 candidates; union, dedup, lọc đã xem, pool khoảng 200–300; weighted ranking, sequence/popularity; re-rank diversity/novelty/freshness, MMR; trả Top-K. | HYBRID-001/002 |
| 10 | Offline ingest/feature/train/evaluate/save; Online UI Streamlit hoặc React, FastAPI `/recommend`, `/similar`, `/feedback`, PostgreSQL, FAISS, Redis. Feedback lưu để retrain định kỳ. | API, UI, OPS, E2E |
| 11 | RMSE/MAE cho rating prediction; Precision@K/Recall@K/NDCG@K; Coverage/Diversity/Novelty; Latency/Cache hit; khuyến nghị temporal split. | SPLIT-001, EVAL-001, OPS-002 |

**Cần phân biệt:** Nhiều công nghệ/thuật toán trong slide là thiết kế đề xuất, chưa phải sản phẩm đã hiện thực. Bộ file này cũng chưa hiện thực chúng. K=10 chỉ là ví dụ ở slide 2; các candidate counts ở slide 9 là giá trị đề xuất ban đầu, có thể được chỉnh sau benchmarking.

**Tài liệu ngoài để kiểm tra về sau, không phải yêu cầu mới trong slide:** https://grouplens.org/datasets/movielens/25m/ ; https://developer.themoviedb.org/ ; https://developer.imdb.com/ . Phải kiểm tra điều khoản/giấy phép nguồn trước khi thu thập và lưu trữ dữ liệu.
