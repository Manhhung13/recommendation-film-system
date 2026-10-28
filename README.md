# Dataset linkage check for Movie Recommendation System

Mục tiêu của gói này là **kiểm tra liên kết dữ liệu trước khi xây recommender**, không phải train model.

## Nguồn dữ liệu

1. **MovieLens 25M**
   - `ratings.csv`
   - `movies.csv`
   - `tags.csv`
   - `links.csv`
   - `genome-scores.csv`
   - `genome-tags.csv`
   - Download: https://files.grouplens.org/datasets/movielens/ml-25m.zip

2. **IMDb Non-Commercial Datasets**
   - Gói kiểm tra chỉ tải `title.basics.tsv.gz` để xác minh `imdbId`.
   - Download directory: https://datasets.imdbws.com/
   - Có thể mở rộng thêm `title.crew.tsv.gz`, `title.principals.tsv.gz`, `name.basics.tsv.gz` sau khi join cơ bản đã đúng.

3. **TMDb API**
   - Dùng `tmdbId` trong MovieLens `links.csv`.
   - Cần Bearer token từ tài khoản TMDb.
   - Docs: https://developer.themoviedb.org/docs/getting-started

## Khóa liên kết cần kiểm tra

```text
MovieLens ratings.csv  --movieId--> movies.csv
MovieLens tags.csv     --movieId--> movies.csv
Tag Genome             --movieId--> movies.csv
MovieLens links.csv    --movieId--> movies.csv
links.imdbId           ---------> IMDb tconst = "tt" + imdbId zero-padded to >= 7 digits
links.tmdbId           ---------> TMDb movie id
```

## Chạy trên Windows PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run_windows.ps1
```

Hoặc chạy tay:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python verify_dataset_linkage.py --workdir .\dataset_linkage_work --sample-size 30 --with-imdb
```

### Kiểm tra TMDb

Tạo API Read Access Token trên TMDb, sau đó:

```powershell
$env:TMDB_BEARER_TOKEN="eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJmNDg3MmU1MmU3YmZmNzFjMWQ2ZjJiZjkzYmE2MGIzYiIsIm5iZiI6MTc5MjgyOTEyNS40ODk5OTk4LCJzdWIiOiI2YWRjNjZjNWQ5MGMxMGY1OGY4ODFjYWUiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.x9V8pmE0dij3TZmFN_AbIMZ0_MqlBlTBTm6y_WjsAug"
python verify_dataset_linkage.py --workdir .\dataset_linkage_work --sample-size 30 --with-imdb --with-tmdb --tmdb-limit 15
```

## Output quan trọng

Sau khi chạy, thư mục `dataset_linkage_work/output/` sẽ có:

- `01_movies_links_sample.csv`: movieId ↔ imdbId ↔ tmdbId
- `02_ratings_sample.csv`: sample rating của các movie được chọn
- `03_tags_sample.csv`: sample user tags
- `04_tag_genome_top_tags_sample.csv`: top semantic tags + relevance của từng movie
- `05_imdb_title_basics_sample.csv`: metadata IMDb match theo tconst
- `06_tmdb_metadata_sample.csv`: metadata TMDb (nếu có token)
- `07_linkage_audit.csv`: bảng audit quan trọng nhất
- `08_movie_enriched_preview.csv`: preview MovieLens + Tag Genome
- `linkage_report.json`: thống kê match / mismatch

## Tiêu chí pass trước khi xây hệ thống

Bạn nên kiểm tra:

1. `ratings.movieId` tồn tại trong `movies.movieId`.
2. `tags.movieId` tồn tại trong `movies.movieId`.
3. Các phim có Tag Genome join được bằng `movieId`.
4. `links.imdbId` map được sang IMDb `tconst`.
5. `links.tmdbId` gọi được TMDb movie detail.
6. Không dùng title string làm khóa join chính nếu đã có ID.
7. Không kỳ vọng tất cả movie đều có Tag Genome; xử lý bằng LEFT JOIN/fallback.

## Kiến trúc dữ liệu sau khi kiểm tra

```text
ratings.csv ──────┐
tags.csv ─────────┤
genome-scores ────┼─ movieId ─> movies.csv ─> movies_enriched
links.csv ─────────┘               │
                                  ├─ imdbId ─> IMDb
                                  └─ tmdbId ─> TMDb
```
