# Product architecture — diễn giải từ slides 2–11

## Offline layer (slide 10)

`MovieLens 25M / Tag Genome / TMDb / IMDb` → ingest raw, validate schema/source → ID mapping qua `links.csv` → Movie Feature Store → temporal split → training candidates (Popularity, CF, SVD, Content, Knowledge, optional SASRec) → evaluation → versioned model artifacts.

Tuyệt đối không join user IDs giữa các nguồn khác dataset. Với Tag Genome, lưu `tag relevance` và vocabulary version. Lưu cả raw lẫn curated. Khi temporal split, feature nào có thể chứa thông tin tương lai phải bị lọc theo thời điểm nếu phụ thuộc tương tác.

## Online layer (slide 10)

`Streamlit or React UI → FastAPI → Recommendation Engine (candidate generation → union/dedup/filter → rank → re-rank) → Top-K`.

- `/recommend`: personalized ranked list; K configurable, demo K=10.
- `/similar`: movie-to-movie recommendations.
- `/feedback`: event persisted with timestamp for subsequent retrain.
- PostgreSQL: users/movies/ratings/events (đề xuất theo slide).
- FAISS: optional vector movie index; Redis: optional Top-K cache (đều chỉ tích hợp sau khi có benchmark).

## Hybrid recipe (slide 9)

- Candidate source quotas: SVD 100, Content 100, Knowledge 50, Popular 30.
- Union removes duplicates; then filters interacted/watched by approved policy. **Không đảm bảo số pool luôn 200–300**, vì số nguồn cộng là 280 trước dedup và một số phim có thể bị loại.
- Weighted ranking uses defined feature normalization and missing-feature fallback; weights are configuration to be validated, not prevalidated optimum.
- Re-rank diversity, novelty, freshness, MMR without violating filters or maximum K.

## Quality (slide 11)

Track RMSE/MAE for rating prediction, Precision@K/Recall@K/NDCG@K for ranking, Coverage/Diversity/Novelty for user experience, Latency/Cache hit for serving. Require real offline report, reproducible dataset versions and no future leakage. Baseline comparisons and thresholds need sign-off; slide does not specify minimums.
