# BÁO CÁO PHÂN TÍCH KẾT QUẢ EDA THỰC NGHIỆM
## Movie Recommendation System — MovieLens 25M, IMDb và TMDb

> **Ngày lập báo cáo:** 14/11/2026  
> **Ngày sinh EDA:** 13/11/2026, 15:52:25 UTC  
> **Phạm vi:** FULL_SCAN MovieLens; FULL EDA có IMDb, TMDb và IMDb extended  
> **Trạng thái:** Đã phân tích dữ liệu thực nghiệm; **chưa** huấn luyện/đánh giá mô hình, **không** phải biên bản hoàn tất task EDA-001 của Agent SDLC.  
> **Kết luận:** **GO cho nghiên cứu feature, kiểm tra giả thuyết, thiết kế split và thí nghiệm baseline**. Không đồng nghĩa sẵn sàng production hoặc đã chứng minh chất lượng Top-N.

---

## 1. Nguồn bằng chứng và cách đọc báo cáo

Báo cáo này dựa trên 23 tệp tổng hợp trong gói người dùng cung cấp **EDA_RESULTS_FOR_ANALYSIS.zip**, gồm hai bộ đầu ra **core** và **full_imdb_extended**: EDA_REPORT.md, eda_summary.json và các CSV tổng hợp. Phần kết quả mở rộng chứa các chỉ số lõi tương ứng với core, vì thế chỉ tổng hợp một lần thay vì cộng đôi.

- **SHA-256 của ZIP phân tích:** 8017fe20ad5ecf086d989e136fd9db72accaeeafb8a4ee8d1f361a9cb1b217de.
- **Phiên bản schema EDA:** research-eda-v1; **generated_at_utc:** 2026-11-13T15:52:25.800922+00:00.
- **Quality baseline tham chiếu:** trạng thái SEMANTIC_SCAN_COMPLETE_ANOMALIES_PENDING_REVIEW; source integrity PASS; SHA-256 của báo cáo baseline theo summary: 65979ca4412e7da1ba27bcae956d99b2b49b0c2ed4ca5d36b5c0864bc723a4cc.
- **Dấu hiệu bất biến raw:** raw_untouched=true; source_stats_before_after_equal=true trong đầu ra EDA. Đây là dữ liệu tự báo cáo của lần chạy; không thay thế việc tự xác minh lại toàn bộ hash raw nếu thay đổi môi trường.
- **Chưa có biểu đồ PNG** vì chart_status=CHARTS_SKIPPED_MATPLOTLIB_NOT_INSTALLED.
- Trong ZIP **không có** ratings_by_year.csv, ratings_by_month.csv, user_activity_bins.csv và các CSV top keywords/cast mặc dù báo cáo EDA nhắc đến một số tên tệp này. Vì vậy, báo cáo **không giả định** đã quan sát đầy đủ các phân bố chi tiết tương ứng.
- Các chỉ số của EDA là **thống kê mô tả toàn lịch sử**, không phải feature as-of tại một cutoff. File summary gắn not_for_training=true.

### Kiểm tra đối chiếu nội bộ

| Phép kiểm tra | Kết quả |
|---|---:|
| Tổng 10 mức rating trong rating_distribution.csv | 25.000.095 = JSON |
| Tổng 8 khoảng số rating/phim | 62.423 = JSON |
| Tổng các nhóm số genre/phim | 62.423 = JSON |
| Tổng số người dùng theo first-rating cohort | 162.541 = JSON |
| Hai bộ core và full có thống kê MovieLens lõi tương ứng | Nhất quán trong ZIP |

**Phân loại phát biểu:** “Quan sát” = tính trực tiếp từ file đã gửi; “Diễn giải” = suy luận hợp lý nhưng chưa kiểm định; “Đề xuất” = bước nghiên cứu cần thực hiện. Không coi diễn giải thành sự thật đã được chứng minh.

---

## 2. Tóm tắt điều hành

| Chỉ số | Giá trị quan sát | Hàm ý chính |
|---|---:|---|
| Ratings | **25.000.095** | Quy mô đủ lớn cho nghiên cứu Collaborative Filtering |
| User có rating | **162.541** | Có cơ sở nghiên cứu phân nhóm hành vi |
| Phim trong catalog | **62.423** | Long-tail lớn, cần đánh giá coverage |
| Phim có ít nhất một rating | **59.047** | **3.376** phim hoàn toàn không có rating |
| Rating trung bình / độ lệch chuẩn | **3,533854 / 1,060744** | Có thiên lệch về phía đánh giá cao |
| Tỷ lệ rating >= 4,0 | **49,8111%** | Có thể thử nhãn positive, không tự động chốt threshold |
| Density / sparsity quan sát | **0,246396% / 99,753604%** | Phải dùng biểu diễn sparse, không coi missing là dislike |
| Top 1% phim nhận | **48,9503%** ratings | Tập trung tương tác cực mạnh |
| Top 10% phim nhận | **94,5474%** ratings | Popularity bias / head-tail rất đáng kể |
| Gini số rating theo phim | **0,945039** | Mức mất cân bằng rất cao |
| Gini số rating theo user | **0,589469** | User cũng không đồng đều |
| Phim có dưới 10 ratings | **38.093 (61,024%)** | Cần content fallback / ít dữ liệu item |
| Phim không có thể loại MovieLens | **5.062 (8,109%)** | Cần mask thiếu genre và fallback |
| Phim có tag MovieLens | **45.251 (72,491%)** | Tag phủ tương đối rộng nhưng không đồng nhất |
| Phim có Tag Genome | **13.816 (22,133%)** | Không thể yêu cầu Genome với toàn catalog |
| Phim có IMDb và TMDb details sạch | **61.247 (98,116%)** | Metadata có độ phủ cao ở *snapshot hiện tại* |

**Quyết định nghiên cứu đề xuất:** bắt đầu bằng MovieLens-only + baseline Popularity và ItemKNN/ALS; tiếp theo thử MovieLens genres, Tag Genome có mask, IMDb và TMDb sạch, rồi Hybrid. Phải báo cáo chất lượng theo nhóm **head/tail** và **user history size**, không chỉ NDCG trung bình.

---

## 3. EDA hành vi người dùng

### 3.1. Mức độ hoạt động (số rating mỗi user)

| Phân vị | Số rating/user |
|---|---:|
| Min (p0) | 20 |
| p25 | 36 |
| Median (p50) | 71 |
| p75 | 162 |
| p90 | 353 |
| p95 | 554 |
| p99 | 1.228 |
| Max | 32.202 |

**Quan sát:** mỗi user có ít nhất 20 ratings trong snapshot; một nhóm nhỏ đánh giá số lượng phim rất lớn. Top 1% user đóng góp **12,1421%** tổng ratings.

**Diễn giải:** đây là bộ dữ liệu có **selection bias về người dùng đã hoạt động**, không đại diện cho người mới tham gia với 0–5 tương tác. Không thể kết luận cold-start thật trong sản phẩm sẽ dễ chỉ vì p0=20.

**Đề xuất:**
1. Tạo các cohort theo **số lịch sử trước cutoff T**: 0, 1–4, 5–9, 10–19, 20–49, 50–199, >=200.
2. Thử nghiệm giả lập cold-start bằng cách chỉ cho mô hình nhìn thấy 1/3/5/10 rating đầu của user; giữ phần sau làm nhãn.
3. Không dùng tổng rating toàn lịch sử để phân nhóm tại thời điểm T, vì sẽ nhìn trước tương lai.

### 3.2. Thiên lệch thang điểm người dùng

- Overall mean rating = **3,534**, std = **1,061**.
- Phân vị trung bình rating theo user: p10 **3,096**; p25 **3,399**; median **3,700**; p75 **4,000**; p90 **4,254**.
- Phân vị std rating theo user: p10 **0,613**; median **0,900**; p90 **1,252**.
- Rating >=4,0 = **12.452.811 / 25.000.095 = 49,811%**; đây là tín hiệu positive *giả định*, không phải số lần user thật sự đã thích/phủ định các phim không đánh giá.

**Diễn giải:** có sự khác biệt về mức hào phóng/khắt khe giữa các user. Xếp hạng sở thích thể loại bằng rating trung bình thô dễ nhầm giữa **user rating bias** và preference.

**Đề xuất feature:** count, mean, std, rating-event recency, residual tương đối với user baseline, confidence/shrinkage theo số mẫu; tính **chỉ trên lịch sử H_u(T)**.

### 3.3. Khoảng trải dài hoạt động

Khoảng cách giữa rating đầu và cuối của mỗi user, trên **toàn lịch sử**:

| Phân vị | Ngày | Diễn giải |
|---|---:|---|
| p10 | 0,00471 | ~6,78 phút |
| p25 | 0,01075 | ~15,48 phút |
| median | 0,05034 | ~1,21 giờ |
| p75 | 40,26656 | ~40,27 ngày |
| p90 | 576,71824 | ~1,58 năm |

**Phát hiện đáng chú ý:** ít nhất một nửa user có rating đầu–cuối cách nhau không quá ~1,21 giờ. Điều này có thể liên quan đến việc chấm điểm theo đợt, nhập lại lịch sử hoặc kiểu tham gia bộ dữ liệu; **chưa có bằng chứng** khẳng định nguyên nhân. Rating timestamp là **thời điểm đánh giá**, không phải thời điểm xem.

**Việc phải kiểm định trước sequence model:**
- Histogram khoảng cách sự kiện theo từng user, tỷ lệ rating cùng timestamp, số rating/ngày.
- So sánh burst-session với user rating kéo dài nhiều tháng.
- Chỉ định nghĩa event sequence, **không** tự gọi là viewing sequence hoặc watch session.

---

## 4. EDA đặc điểm phim và mất cân bằng popularity

### 4.1. Phân bố số rating/phim

| Số rating của phim | Số phim |
|---|---:|
| 0–9 | **38.093** |
| 10–19 | 5.900 |
| 20–49 | 5.254 |
| 50–99 | 2.850 |
| 100–499 | 4.940 |
| 500–999 | 1.592 |
| 1.000–4.999 | 2.571 |
| >=5.000 | 1.223 |
| **Tổng** | **62.423** |

- **3.376 phim (5,408%)** không có rating; là tập con của khoảng 0–9.
- Median phim nhận **5 ratings**; p75 **31**; p90 **365**; p99 **9.477**; max **81.491**.
- Top 1% phim nhận **48,950%** và top 10% phim nhận **94,547%** ratings.
- Gini popularity = **0,9450**. Đây là đặc điểm mang tính quyết định đối với lựa chọn thuật toán và đánh giá.

**Tác động:** các mô hình dựa vào đồng tương tác hoạt động thuận lợi cho phim head, nhưng dữ liệu co-rating nghèo ở tail. Một phép chia train/test ngẫu nhiên hoặc negative sampling không phù hợp có thể báo cáo metric đẹp trong khi bỏ qua phần lớn catalog.

**Đề xuất:** tối thiểu đo Recall@10, NDCG@10, HitRate@10, catalog coverage, tỷ trọng recommendation tail, novelty và intra-list diversity; chia kết quả theo bucket 0, 1–9, 10–49, 50–499, >=500 **tính từ train trước T**. Không coi 0 rating = phim kém.

### 4.2. Ví dụ phim phổ biến (không đồng nghĩa phim tốt nhất)

| Phim | Rating count | Mean rating |
|---|---:|---:|
| Forrest Gump (1994) | 81.491 | 4,048 |
| The Shawshank Redemption (1994) | 81.482 | 4,414 |
| Pulp Fiction (1994) | 79.672 | 4,189 |
| The Silence of the Lambs (1991) | 74.127 | 4,151 |
| The Matrix (1999) | 72.674 | 4,154 |

Nguồn: top_movies_aggregate.csv. Số rating lớn không chứng minh phim có hiệu ứng sở thích phổ quát hoặc chất lượng khách quan cao; cần kiểm soát độ tuổi phim, exposure và thiên lệch chọn đánh giá.

---

## 5. EDA thể loại (genre) và tín hiệu sở thích

### 5.1. Độ phủ và phân bố

- **20 nhãn** trong thống kê MovieLens, bao gồm **(no genres listed)**; nhãn thiếu không phải một genre sở thích thực.
- **5.062 phim (8,109%)** không có genre.
- **25.569 phim** có 1 genre; **18.326** có 2; **9.852** có 3.
- Số phim theo genre (một phim có thể được đếm nhiều lần): Drama **25.606**; Comedy **16.870**; Thriller **8.654**; Romance **7.719**; Action **7.348**; Horror **5.989**; Documentary **5.605**.
- Tồn tại **168 cặp genre** quan sát trong bộ tổng hợp; cặp nhiều nhất Drama–Romance (**4.654 phim**) và Comedy–Drama (**4.603 phim**).

### 5.2. Rating theo genre (thống kê quan sát)

| Genre | Lượt rating gắn nhãn genre | Mean | Share rating >=4 |
|---|---:|---:|---:|
| Drama | 10.962.833 | 3,677 | 55,611% |
| Comedy | 8.926.230 | 3,424 | 45,339% |
| Action | 7.446.918 | 3,467 | 46,535% |
| Crime | 4.190.259 | 3,685 | 55,915% |
| Horror | 1.892.183 | 3,294 | 40,910% |
| War | 1.267.346 | 3,791 | 60,934% |
| Film-Noir | 247.227 | 3,926 | 67,487% |

**Quan trọng:** vì phim có nhiều genre, tổng lượt rating trong bảng **không bằng 25 triệu**. Film-Noir có mean cao nhất trong các ví dụ này nhưng không chứng minh tất cả user yêu Film-Noir hơn Horror; cần hiệu chỉnh user/item/popularity và độ tin cậy.

**Đề xuất tạo user genre affinity tại T:**
- Từ phim user đánh giá trước T, dùng genre multi-hot có cơ chế phân bổ trọng số 1/số genre để hạn chế phim nhiều genre được tính quá mức.
- Ước lượng sở thích bằng rating residual (rating − baseline user) hoặc mức positive tương đối có shrinkage.
- Xuất đồng thời số mẫu hữu hiệu cho từng genre và mask thiếu genre.
- Kiểm nghiệm **predictive gain trên validation**, không quyết định từ raw mean.

---

## 6. Tags và Tag Genome

| Nguồn tín hiệu | Kết quả |
|---|---:|
| Tag events | **1.093.360** |
| Tag rỗng | **9** |
| Phim có ít nhất một tag | **45.251 / 62.423 = 72,491%** |
| Tag Genome — phim | **13.816 / 62.423 = 22,133%** |
| Tag Genome — số tag | **1.128** |
| Genome relevance scores | **15.584.448** |
| Genome relevance mean | **0,116368** |

**Nhận xét:**
- Tags tự do có khả năng cung cấp signal ngôn ngữ/ngữ nghĩa nhưng có thể rất nhiễu; không mặc nhiên xem tag là xác nhận user thích phim.
- Genome là không gian tag relevance hấp dẫn cho Content-Based nhưng phủ **22,13% catalog**. Vì vậy mọi feature Genome phải có **mask coverage**; không điền 0 để biểu diễn “không có Genome”.
- Số tag events trong năm **2018 là 319.688**, bằng khoảng **29,24%** tổng tag events. Cần kiểm tra lệch thời gian nguồn tag trước khi dùng.
- Snapshot Genome đang quan sát không chứng minh score từng phim đã tồn tại ở thời điểm rating lịch sử.

**Gợi ý ablation:** genres-only → genres+Genome ở cùng tập phim có Genome → thêm fallback và đo lại trên **toàn catalog**. Phải báo cáo cả metric trong subpopulation lẫn coverage tổng.

---

## 7. Metadata IMDb, TMDb: coverage sạch và vấn đề mơ hồ

### 7.1. Độ phủ metadata

| Điều kiện | Số phim | % toàn catalog |
|---|---:|---:|
| IMDb mapping hợp lệ | **62.294** | **99,793%** |
| TMDb mapping hợp lệ | **61.265** | **98,145%** |
| TMDb details hợp lệ sau semantic quarantine | **61.262** | **98,140%** |
| Cả IMDb + TMDb mapping hợp lệ | **61.250** | **98,121%** |
| Cả IMDb + TMDb details sạch | **61.247** | **98,116%** |

**Phân biệt đúng:** 61.250 là coverage ở tầng **mapping**; 61.247 là coverage kết hợp sau khi trừ **3 TMDb details payload có genre trùng**. Không dùng 61.250 như số phim đã sạch nội dung TMDb.

### 7.2. Quy tắc cách ly/fallback cho EDA và mô hình

| Nhóm | Bằng chứng | Quy tắc thực thi đề xuất |
|---|---|---|
| TMDb mapping mơ hồ | **198 phim** | Bỏ **chỉ** metadata TMDb chưa xác thực; vẫn giữ MovieLens movieId, genres, ratings và IMDb hợp lệ |
| Genre trong movie_details bị duplicate | **3 movieId: 74056, 152894, 161316** | Cách ly **payload details**, giữ các bảng keywords/credits riêng nếu hợp lệ; không xóa phim/rating |
| TMDb không thu thập được | **854 ID ghi nhận 404** trong checkpoint và crawl report | Gắn missing-as-of-crawl, không bịa metadata hoặc coi là phim không tồn tại |
| IMDb runtimeMinutes bằng 0 | **4 title nguồn**, không liên kết với MovieLens (đã đối chiếu trước EDA) | Ghi anomaly cấp nguồn, không loại rating MovieLens |
| Phim thiếu IMDb/TMDb metadata | Theo các denominator ở bảng trên | Dùng fallback MovieLens/content khác; luôn xuất mask và confidence |

**Lưu ý đếm:** các nhóm khác nhau có thể giao nhau. Không cộng 198 + 3 + 854 rồi tuyên bố đó là tổng phim phải xóa. Metadata là feature tùy chọn; **không loại toàn bộ rating hợp lệ** khi một nguồn thiếu.

### 7.3. Kiểm tra tính nhất quán TMDb

- **62.281** TMDb ID mục tiêu.
- **61.427** completed, **854** failed; hai tập không giao nhau và phủ toàn bộ target.
- Mỗi file movie_details.jsonl, keywords.jsonl, credits.jsonl có **61.427 dòng và 61.427 ID duy nhất**, không trùng TMDb ID trong từng file.
- 854 lỗi được lưu theo loại HTTP_404_OR_NOT_FOUND; đây là nhãn lỗi đã ghi trong evidence, **không** chứng minh 854 phim vĩnh viễn không tồn tại.
- **3** details bị cách ly do duplicate genre ID–name; các trường genre trùng giống hệt nhau theo kiểm tra payload thực tế, nhưng vẫn cách ly thay vì sửa raw.

### 7.4. Chất lượng các trường metadata IMDb

Trong **62.294** IMDb basics target rows:

- Runtime thiếu hoặc bằng 0: **154 (~0,247%)**. **Khác** với bốn title IMDb toàn nguồn có runtime bằng 0 không liên kết MovieLens.
- IMDb release year thiếu: **5**.
- Năm IMDb khác năm suy từ title MovieLens: **4.458 (~7,156%)**; là *disagreement cần điều tra*, không phải 4.458 lỗi đã chứng minh.
- Có IMDb director: **62.138 phim**; writer: **59.063 phim**.
- IMDb principal rows: **1.148.190** trên **62.263 phim**; 376.590 person IDs được tham chiếu, **20** không tìm thấy tên trong snapshot.

**Đề xuất:** giữ năm từ từng nguồn với provenance và precision riêng, phân nhóm nguyên nhân mismatch (re-release, title convention, năm IMDb khác, dữ liệu thực sự sai) trước khi dùng chính sách release eligibility. Với runtime thiếu dùng mask, không đặt 0 phút.

### 7.5. Chất lượng TMDb details và chiều rộng feature

Trong **61.262** details hợp lệ:

- Thiếu overview: **97 (~0,158%)**.
- Thiếu release_date: **15 (~0,025%)**.
- Thiếu genres tại tầng details hợp lệ: **0**.
- Movie có director TMDb: **61.055**.
- TMDb keyword unique IDs: **29.533**; keyword items: **305.083**.
- TMDb cast credit rows: **1.375.264**; crew credit rows: **1.698.226**; distinct cast people: **518.661**; distinct directors: **26.931**.

**Diễn giải:** nguồn này đủ giàu cho nghiên cứu keyword/overview/actor/director features, nhưng dimensionality cao và long-tail diễn viên/keyword cần regularization, giảm chiều, và ablation. Không suy ra tên người nổi tiếng là đặc trưng giúp ranking trước khi đo held-out gain.

---

## 8. Temporal EDA và nguy cơ leakage (ưu tiên cực cao)

- Khoảng rating UTC: **1995-01-09 11:46:49 → 2019-11-21 09:15:03**.
- **902** rating có timestamp trước năm hiển thị trong title phim; đây là cờ *proxy year conflict*, không tự động kết luận rating bất hợp lệ.
- Summary ghi **61.262 / 61.262 TMDb details hợp lệ được fetched sau timestamp rating cuối cùng**. Đây là tín hiệu rất rõ rằng metadata TMDb quan sát từ crawl hiện tại là **snapshot hậu nghiệm**, không thể tự nhận là đã sẵn có tại thời điểm user rating.
- IMDb hiện là bản xuất sau kỳ rating lịch sử; không có bằng chứng as-of cho từng metadata field.
- User first-rating cohorts có đỉnh năm 1996 (**23.028 user**), năm 2015 (**11.027**) và 2016 (**9.484**). Đây là năm **rating đầu ghi nhận trong tập**, không phải ngày đăng ký hay năm sinh user.
- Trong ZIP thiếu các bảng ratings_by_month/year và user_activity_bins chi tiết, do đó chưa thể quyết định cutoff tối ưu dựa trên phân bố tương tác từng tháng.

**Bắt buộc khi nghiên cứu tiếp:**
1. Định nghĩa lịch sử **H_u(T) = các rating của u tại t < T**; mọi user mean/genre affinity/neighbor/popularity phải tính từ H(T).
2. Chia train/validation/test theo thời gian, có kiểm tra tied timestamps và các phim chưa phát hành tại T.
3. Tách hai chế độ phân tích: **historical-strict** (chỉ feature có bằng chứng tồn tại trước T) và **retrospective-enriched** (sử dụng snapshot nội dung hiện tại, gắn giả định và báo cáo riêng).
4. Không đưa TMDb popularity, vote_count, revenue, current ratings/known-for hoặc thông tin cộng đồng sau T vào feature hồi cứu.
5. Không dùng biểu đồ EDA toàn thời gian như feature training. Không dùng test labels để hiệu chỉnh threshold, candidate set hoặc chọn cutoff.

---

## 9. Feature Dictionary đề xuất từ dữ liệu thật

### 9.1. User features — phải tính trước T

| Feature | Nguồn | Cách tính gợi ý | Rủi ro/độ tin cậy |
|---|---|---|---|
| user_history_count | MovieLens ratings | count(H_u(T)) | Cold-start khi ít lịch sử |
| user_mean_rating, user_std_rating | ratings | mean/std trên H_u(T) | Cần min-count/shrinkage |
| user_positive_rate | ratings | share(r >= ngưỡng) trên H(T) | Ngưỡng là giả thuyết cần thử |
| user_rating_recency | ratings.timestamp | T − last_rating_event_time | Không suy ra last watch time |
| user_activity_tenure | ratings.timestamp | max_time − min_time trong H(T) | Burst artifact |
| user_genre_affinity | ratings + MovieLens genres | shrunk baseline-adjusted weighted genre preference | Missing genre, đa nhãn, user bias |
| user_genre_diversity | genre exposure quan sát | entropy của genre từng phim user đã rating | Không phải tất cả phim đã xem |
| user_popularity_tendency | train-only movie counts | percentile popularity của phim được rating | Tính popularity ở trước T |
| user_genome_affinity | ratings + Genome | weighted semantic vector khi có Genome | Genome chỉ phủ 22,13% catalog, thiếu as-of |
| user_preference_drift | ratings trước T chia cửa sổ | cosine/divergence giữa window cũ và mới | Chỉ dùng user đủ sự kiện |

**Không có trong dữ liệu trực tiếp:** tuổi, giới tính, nghề nghiệp; không suy đoán đây là thuộc tính đo được.

### 9.2. Movie features

| Feature | Nguồn | Cách dùng | Fallback/mask |
|---|---|---|---|
| movieId, genres multi-hot | MovieLens movies | Content baseline | Genre missing → mask |
| title / year proxy | MovieLens movies | Mô tả, search, kiểm tra năm | Không tự khẳng định release exact |
| rating_count_before_T, Bayesian popularity | MovieLens ratings train | CF baseline / item bias | 0 history → content |
| tag activity | MovieLens tags | Side information, topical signal | Tag missing → mask |
| tag_genome_vector | Tag Genome | Semantic content embedding | Genome missing → mask |
| IMDb runtime, year, genres | IMDb sạch | Cấu trúc content | Missing/invalid → mask |
| IMDb directors/writers/principals | IMDb sạch | Creator affinity | Count threshold/shrinkage |
| TMDb overview/keywords | TMDb sạch | NLP / semantic retrieval | Missing/payload issue → mask |
| TMDb genres/cast/crew | TMDb sạch | Multi-source content & entities | Mapping/payload quarantine |
| metadata_available_at_T | evidence timestamps | Historical feature eligibility | Unknown → strict excludes |

### 9.3. Interaction features

- Genre match(user,item), vector similarity(user genre/profile, movie genres), Genome cosine similarity nếu cả hai có mask hợp lệ.
- Popularity-stratified ranker signals và confidence-based gating giữa CF và content.
- Tránh tạo all-pairs user–user; chỉ chọn candidate neighbors/items có giới hạn.

**Không chốt mô hình hay trọng số Hybrid tại EDA.** Trọng số phải được chọn trên validation riêng theo cohort/candidate policy và so sánh với single-model baseline.

---

## 10. Danh sách vấn đề được ưu tiên và quyết định thiết kế

| Ưu tiên | Phát hiện EDA | Tác động | Việc tiếp theo / tiêu chí kiểm chứng |
|---|---|---|---|
| **P0** | 99,754% sparsity; 61,02% phim <10 ratings | CF khó với tail | Sparse baseline + item/head-tail evaluation |
| **P0** | Top 10% phim nhận 94,55% ratings | Popularity bias & coverage | Coverage, novelty, tail Recall, popularity baseline |
| **P0** | TMDb details fetched sau tất cả rating lịch sử | Temporal leakage | Hai evaluation modes; split T + evidence availability |
| **P1** | p50 user activity span ~1,21 giờ | Không thể suy ra watch session | Khảo sát inter-event time và timestamp ties |
| **P1** | Tag Genome chỉ phủ 22,13% catalog | Coverage failure | Missingness mask + genre fallback |
| **P1** | 5.062 phim thiếu MovieLens genre | Content feature thiếu | Fallback từ metadata sạch, coverage report |
| **P1** | 4.458 bất đồng năm IMDb và title | Sai release eligibility tiềm tàng | Phân nhóm/đối chiếu precision của năm |
| **P1** | 198 phim mapping TMDb mơ hồ, 3 details quarantine | Sai join/feature | Field-level mask; kiểm tra không nhân đôi rating |
| **P2** | Rating >=4 chiếm 49,81% | Threshold phụ thuộc định nghĩa bài toán | So sánh 3,5 / 4,0 / 4,5 |
| **P2** | Thiếu bảng CSV time bins trong ZIP; không có PNG | Chưa đủ để phân tích trend/seasonality | Xuất bổ sung thống kê aggregate an toàn |

---

## 11. Kế hoạch thực nghiệm RESEARCH → EDA bổ sung → MODELING

| Bước | Thực hiện | Đầu ra cần có |
|---|---|---|
| **R1. Định nghĩa câu hỏi** | Bài toán Top-N implicit từ explicit rating; chọn positive thresholds 3,5/4,0/4,5 để làm sensitivity | Problem definition + hypotheses |
| **R2. Đối chiếu thông tin thời gian** | Tạo ratings theo tháng/năm, event gaps, timestamp ties, first-rating cohorts; kiểm tra release mismatches | Temporal diagnostics, cutoff candidates |
| **R3. Time-based split** | Chọn T và horizon từ development data; freeze validation/test; dùng H(T) | Train/val/test protocol, eligible denominators |
| **R4. Độ khó cold-start** | Cắt ngắn lịch sử user ở 1/3/5/10; phim phân bucket theo train-only popularity | Evaluation cohorts |
| **R5. Baseline** | Popularity/mean with Bayesian shrinkage, ItemKNN, ALS/implicit MF, genre content | Mốc so sánh xác thực |
| **R6. Feature ablation** | genres → +Genome → +IMDb → +TMDb → Hybrid, so sánh chung tập ứng viên và theo coverage | Bảng NDCG/Recall/Coverage/Diversity |
| **R7. Báo cáo kết quả** | Bootstrap/cụm theo user, so sánh head/tail, cold/active, missingness cohorts | Kết luận feature hữu ích hay không |

### Tối thiểu phải đáp ứng trước khi tuyên bố mô hình tốt

- Có baseline và split theo thời gian; không lẫn dữ liệu tương lai trong user/movie learned statistics.
- Không coi ô chưa rating là negative ground truth; negative sampling chỉ là giao thức đánh giá có giới hạn, phải công bố.
- Báo cáo top-N metrics cùng catalog coverage, novelty/diversity và độ phủ features.
- Đối chiếu chính xác số bản ghi mỗi tập, người dùng có train history, số positive đánh giá được và tỷ lệ phim bị loại vì không đủ as-of metadata.
- Các kết quả trong báo cáo EDA hiện tại **không** phải kết quả dự đoán hay kiểm định nhân quả.

---

## 12. Kết luận và quyết định chuyển giai đoạn

**Kết luận có bằng chứng:** Dữ liệu tương tác MovieLens có quy mô đủ lớn và đã hoàn thành EDA mô tả trên toàn tập; mapping/content metadata sạch đạt độ phủ snapshot cao; bất thường đã được nhận diện và có thể mask/fallback theo nguồn. Không có bằng chứng từ các file hiện có rằng bắt buộc phải loại bỏ rating hợp lệ để bắt đầu nghiên cứu.

**Hạn chế nổi bật:** sparsity 99,754%, popularity concentration 94,55% ở top 10% phim, p50 user rating span ~1,21 giờ, Genome chỉ phủ 22,13%, và mọi TMDb clean details đều mang fetch time sau giai đoạn ratings lịch sử. Đây là các vấn đề nghiên cứu có khả năng ảnh hưởng trực tiếp đến cách đánh giá Top-N và chiến lược Hybrid.

**Quyết định:** **GO — Research, temporal diagnostics, feature engineering theo cutoff và baseline experiments; NO-GO cho việc tuyên bố performance/model tốt nhất ở thời điểm hiện tại.**

*Báo cáo chỉ sử dụng các aggregate đã cung cấp, không chứa userId/histories, không thay đổi raw data và không gán trạng thái hoàn tất cho task RESEARCH-001/EDA-001 chính thức.*
