# Bản đồ acceptance tests đề xuất

Các tên test dưới đây là **test cần xây**, chưa phải test đã tồn tại.

- DATA-001: rating/movies/tags/links đúng schema, ID không âm/không trùng bất hợp lệ, timestamp parse được.
- DATA-002: map `movieId↔tmdbId↔imdbId`, không join qua title, missing IDs được xử lý; không join user IDs.
- DATA-003: Tag Genome: `tagId`, `relevance` và vocabulary khớp; giữ version.
- DATA-004/005: metadata có provenance, API/dump fallback, id mapping chính xác, null/duplicates được xử lý.
- DATA-006: feature store join preserving keys, missingness flags và schema version.
- SPLIT-001: temporal ordering; training history không biết tương lai của holdout, coverage của user có ít history.
- BASE-001: popular baseline deterministic, unique Top-K, fallback cold user.
- CF-001/002, MF-001: train trên observed history, loại interacted items và inference được với missing user/item.
- CONTENT-001: vectorization TF-IDF/embedding, cosine, case cold-item, giới hạn index memory.
- KNOW-001: filter `genres/year/runtime/actor/director`, điều kiện AND, explainability grounded metadata.
- SEQ-001: events sorted by timestamp, causal masking, padding, no future interactions at train/inference.
- HYBRID-001: source quota 100/100/50/30, candidate union/dedup, approved exclusion, item eligibility, deterministic rank input.
- HYBRID-002: top-K sorted, feature normalization, MMR/dedup, no candidate outside eligible set, strategy when pool < K.
- EVAL-001: RMSE/MAE; P@K/R@K/NDCG@K; Coverage/Diversity/Novelty, reproducibility, baseline and metric definitions.
- API-001/002: schema contracts, invalid K, missing user, feedback event persistence and timestamps, privacy authorization.
- UI-001: end-to-end display Top-K, rating/feedback path and fallback states.
- OPS-001/002: cache invalidation, metrics latency/cache-hit and graceful fallback without Redis/FAISS.
- E2E-001: full offline→online example; checks actual data/model artifact versions and no leakage.

No fixed quality/latency threshold is authored by slide; threshold values must be explicitly agreed and validated with empirical baseline.
