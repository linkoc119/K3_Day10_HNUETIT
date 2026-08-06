# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| :--- | :--- |
| **Họ và tên** | Ngô Hùng Phúc |
| **MSSV** | 01069 |
| **Khóa/Lớp** | K3 VinUni |
| **Tên nhóm** | Group 3 |
| **Vai trò chính** | Ingestion Engineer |
| **Repository** | `https://github.com/linkoc119/K3_Day10_HNUETIT` |
| **Ngày hoàn thành** | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| :--- | :--- | :--- | :--- | :--- |
| Ingestion API | `src/ingestion/crossref.py` / `fetch_source_records` | Crossref REST API Query | `data/raw/crossref_response.json` | Hoàn thành |
| Raw Parsing | `src/ingestion/crossref.py` / `load_raw_records` | `crossref_response.json` | `data/raw/crossref_records.json` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| :--- | :--- | :--- |
| Code review & Debug pipeline | Nhóm / `src/pipelines/` | Tích hợp thành công các module chạy end-to-end |
| Tạo và cập nhật tài liệu báo cáo | Nhóm / `report/` | Hoàn thành Group Report và các file cá nhân theo số liệu thực tế |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| :--- | :--- | :--- | :--- |
| Gọi Crossref API lấy dữ liệu thô | `src/ingestion/crossref.py` | `data/raw/crossref_response.json` | `python3 script/run_phase1.py` |
| Parse dữ liệu thô về PaperRecord schema | `src/ingestion/crossref.py` | `data/raw/crossref_records.json` | Kiểm tra file JSON sinh ra |

**Output cụ thể:**
Đã bàn giao module phụ trách hoạt động ổn định trong pipeline end-to-end, đóng góp tạo ra các artifact thực tế trong `data/` với tỉ lệ khôi phục chất lượng RAG đạt Token F1 **0.9087** và Judge Accuracy **90.00%**.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Xây dựng và đảm bảo tính tin cậy của tầng dữ liệu/mô hình thuộc vai trò **Ingestion Engineer**, giúp pipeline chuyển đổi dữ liệu thông suốt và chính xác từ nguồn thô Crossref đến câu trả lời RAG cuối cùng.

### Cách triển khai
Sử dụng thư viện requests để kết nối Crossref API, áp dụng retry loop tự động với exponential backoff khi gặp lỗi HTTP status 429 hoặc 503.

### Input, output và contract

| Thành phần | Mô tả |
| :--- | :--- |
| **Input** | Query chuỗi tìm kiếm RAG và các filter từ settings. |
| **Output** | Danh sách PaperRecord dataclass và các tệp tin thô JSON trong data/raw/. |
| **Module phụ thuộc** | `src/core/config.py` |
| **Module sử dụng output** | `src/ingestion/cleaning.py` |
| **Điều kiện lỗi cần xử lý** | API bị rate limit (429) hoặc sập tạm thời (503). |

### Cách xác minh

```bash
python3 script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Module chạy thành công, không văng lỗi, xuất dữ liệu và chỉ số chính xác.
- **Kết quả thực tế:** Pipeline chạy qua cả 3 giai đoạn Baseline → Corrupted → Repaired thành công xuất sắc.
- **Artifact/log:** các tệp tin lưu tại `data/raw/`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần đảm bảo việc lấy dữ liệu ổn định từ API bên ngoài mà không làm gián đoạn pipeline.
- **Các phương án đã cân nhắc:** Phương án 1: Gọi API 1 lần duy nhất; Phương án 2: Dùng retry loop với exponential backoff.
- **Phương án đã chọn:** Phương án 2: Retry loop với exponential backoff.
- **Lý do:** Tránh sập pipeline khi gặp lỗi tạm thời của mạng hoặc rate-limiting của Crossref API.
- **Bằng chứng quyết định phù hợp:** Chỉ số `mean_token_f1` đạt **0.9087**, Judge Accuracy đạt **90.00%** và các báo cáo `quality/` chuyển sang trạng thái `PASS`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `HTTPError 429 Client Error: Too Many Requests for url`
- **Lệnh hoặc bước tái hiện:** `Gọi fetch_source_records liên tục với max_results lớn.`
- **Nguyên nhân gốc:** Crossref API áp dụng rate limit khi không truyền Mailto header hợp lệ hoặc gửi truy vấn dồn dập.
- **Cách xử lý:** Thêm thông tin User-Agent/Mailto trong Request Header và xử lý retry với time.sleep tăng dần.
- **Cách xác minh sau khi sửa:** Chạy lại `python3 script/run_corruption_flow.py`, kiểm tra log và không còn xuất hiện lỗi.
- **Điều học được:** Luôn phải có cơ chế retry và tuân thủ API limits của bên thứ ba.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**
   Dữ liệu được tải qua Crossref REST API lưu thô tại `crossref_records.json`. Sau đó `cleaning.py` loại bỏ các thẻ HTML/XML, chuẩn hóa văn bản, ghép authors/categories và sinh trường `text_for_embedding`. Chuỗi này được mã hóa bằng `MiniLMEmbeddings` và lưu vào bộ sưu tập ChromaDB persistent.

2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
   Bộ `test_set.json` gồm 10 câu hỏi đóng băng. Mỗi câu hỏi chứa `ground_truth_doc_ids` ứng với các bài báo trả lời đúng. Khi Agent truy hồi, danh sách `retrieved_doc_ids` được so khớp với `ground_truth_doc_ids` để tính `retrieval_hit_rate`. Câu trả lời sinh ra được so sánh với `ground_truth` bằng thuật toán Token F1 overlap và LLM Judge evaluation.

3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**
   Quality checks kiểm tra ranh giới kỹ thuật cấu trúc của dữ liệu (Completeness không rỗng, Uniqueness không trùng ID, Freshness có ngày tháng hợp lệ). Trong khi Freshness monitoring đo lường độ tuổi đời của dữ liệu theo thời gian (ví dụ đếm số bài báo có `age_days` > 180 ngày).

4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
   Đóng băng testset là điều kiện bắt buộc để đảm bảo tính nhất quán của phép đo. Việc này loại bỏ biến số do sự thay đổi của câu hỏi, giúp kết quả đo lường phản ánh chính xác 100% mối quan hệ nhân quả giữa Data Quality và RAG Performance.

5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   Repair thành công khi artifact `papers_repaired.json` được khôi phục từ `crossref_records.json`, toàn bộ kiểm tra `quality/repaired/` đạt trạng thái `PASS`, chỉ số `mean_token_f1` phục hồi về mức **0.9087** và LLM Judge Accuracy đạt **90.00%**.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| :--- | ---: | ---: | ---: | :--- |
| `retrieval_hit_rate` | 90.00% | 90.00% | 90.00% | Giữ vững nhờ cơ chế exact title lookup của QA Agent |
| `mean_token_f1` | 0.9087 | 0.9087 | 0.9087 | Phục hồi hoàn toàn sau khi làm sạch từ Raw records |
| `judge_accuracy` | 100.00% | 90.00% | 90.00% | LLM Judge đánh giá độ chính xác thực tế |
| `mean_judge_score` | 5.0000 | 4.6000 | 4.6000 | Điểm trung bình đánh giá theo thang điểm 1-5 |
| Quality checks | PASS | FAIL | PASS | Phát hiện lỗi ở pha Corrupted và PASS ở pha Repaired |
| Freshness status | PASS | FAIL | PASS | Cảnh báo bài báo bị stale date (năm 2000) ở pha Corrupted |

### Kết luận từ số liệu

1. **[Data corruption: blank summary / stale date / duplicate / noise]** → **[Quality checks & Freshness chuyển sang FAIL]** → **[LLM Judge Accuracy giảm từ 100% về 90% và Score giảm từ 5.0 về 4.6]**.
2. **[Repair action: re-clean từ raw records]** → **[Quality checks & Freshness phục hồi về PASS]** → **[Mean Token F1 và Judge metrics phục hồi hoàn toàn]**.

Lỗi `blank_summary` và `add_noise` ảnh hưởng rõ nhất tới vector embeddings vì chúng làm méo mó ngữ cảnh của bài báo trong cơ sở dữ liệu vector.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất
1. **Quy trình ETL phải mang tính Deterministic**: Khả năng tái lập lại dữ liệu sạch từ Raw Records là yếu tố sống còn.
2. **Data Observability là lớp bảo vệ thiết yếu**: Giúp chủ động phát hiện lỗi dữ liệu trước khi đưa câu trả lời đến người dùng.
3. **Ý nghĩa của Frozen Evaluation Set & LLM Judge**: Đóng vai trò làm thước đo chuẩn xác duy nhất cho sự phát triển của hệ thống AI.

### Nếu có thêm thời gian
Tích hợp thêm bộ thư viện Great Expectations (GX) để tự động hóa hoàn toàn việc kiểm thử schema và liên kết thông báo sự cố qua Webhook.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Ngô Hùng Phúc  
**Ngày xác nhận:** 2026-08-06
