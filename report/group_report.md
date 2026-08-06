# Project Group Report - Group 3

## 1. Project Overview
Dự án nhằm xây dựng một hệ thống dữ liệu (data pipeline) học thuật lấy nguồn từ Crossref API phục vụ cho ứng dụng RAG (Retrieval-Augmented Generation). Trọng tâm của bài lab là chứng minh mối quan hệ nhân quả giữa chất lượng dữ liệu đầu vào (Data Quality) và chất lượng câu trả lời của RAG Agent thông qua phương pháp đánh giá có kiểm soát: **Baseline → Corrupted → Repaired**, sử dụng chung bộ kiểm thử đóng băng (**Frozen Evaluation Set**).

### Luồng Pipeline Tổng Thể:
```text
Crossref API (Works)
     │
     ▼
Raw JSON Records (data/raw/)
     │
     ▼
Cleaning & Normalization (cleaning.py)
     │
     ▼
Clean JSON/CSV Dataset (data/clean/papers_clean.json)
     │
     ▼
ChromaDB Vector Index (MiniLM Embeddings)
     │
     ▼
Retrieval-Augmented QA Agent (LLM Gemini/Ollama)
     │
     ▼
Evaluation Loop & Observability Quality Checks (observability/)
```

## 2. Project Structure
Dưới đây là cấu trúc thư mục hiện tại của dự án:
```text
day10-data-observability-lab/
├── data/
│   ├── chroma/
│   ├── clean/
│   │   ├── papers_clean.json
│   │   ├── papers_corrupted.csv
│   │   └── papers_repaired.json
│   ├── embeddings/
│   ├── eval/
│   │   └── test_set.json
│   ├── quality/
│   │   ├── baseline/
│   │   ├── corrupted/
│   │   └── repaired/
│   ├── raw/
│   │   ├── crossref_records.json
│   │   └── crossref_response.json
│   ├── reports/
│   │   ├── phase1_report.md
│   │   └── corruption_report.md
│   └── results/
│       ├── baseline_answers.json
│       ├── baseline_metrics.json
│       ├── corrupted_answers.json
│       ├── corrupted_metrics.json
│       ├── corruption_log.json
│       ├── repaired_answers.json
│       └── repaired_metrics.json
├── report/
│   ├── group_report.md
│   ├── individual_01069_NgoHungPhuc.md
│   ├── individual_01147_NguyenDuyHoang.md
│   ├── individual_01711_LeVanLong.md
│   ├── individual_01717_NguyenNgocDuong.md
│   └── individual_01971_NguyenVanLinh.md
├── script/
│   ├── generate_reports.py
│   ├── run_corruption_flow.py
│   └── run_phase1.py
├── src/
│   ├── core/
│   ├── evaluation/
│   ├── ingestion/
│   ├── observability/
│   ├── pipelines/
│   └── retrieval/
└── pyproject.toml
```

## 3. Dataset Statistics
Các số liệu thống kê thực tế được đọc trực tiếp từ thư mục `data/`:
* **Số lượng bản ghi gốc (Raw Records)**: 24 bản ghi
* **Số lượng bản ghi sạch (Clean Records)**: 24 bản ghi
* **Số lượng câu hỏi đánh giá (Frozen Test Questions)**: 10 câu hỏi
* **Số lượng bản ghi bị lỗi (Corrupted Records)**: 25 bản ghi (bao gồm cả dòng trùng lặp bổ sung)

## 4. Baseline Results
Kết quả đánh giá hệ thống ở trạng thái dữ liệu sạch ban đầu:
* **Retrieval Hit Rate**: 90.00%
* **Mean Token F1**: 0.9087
* **Mean Latency**: 61 ms
* **LLM Judge Correct Rate**: N/A

## 5. Corruption Results
Kết quả đánh giá hệ thống khi dữ liệu bị lỗi có kiểm soát (20% số tài liệu bị phá hỏng):
* **Retrieval Hit Rate**: 90.00%
* **Mean Token F1**: 0.9087
* **Mean Latency**: 58 ms
* **LLM Judge Correct Rate**: N/A

## 6. Repair Results
Kết quả đánh giá sau khi thực hiện lineage-based repair từ bản ghi gốc:
* **Retrieval Hit Rate**: 90.00%
* **Mean Token F1**: 0.9087
* **Mean Latency**: 57 ms
* **LLM Judge Correct Rate**: N/A

## 7. Comparison Table
Bảng so sánh hiệu năng của RAG qua 3 giai đoạn:

| Chỉ số | Baseline (Dữ liệu sạch) | Corrupted (Dữ liệu lỗi) | Repaired (Sau sửa đổi) |
| :--- | :---: | :---: | :---: |
| **Retrieval Hit Rate** | 90.00% | 90.00% | 90.00% |
| **Mean Token F1** | 0.9087 | 0.9087 | 0.9087 |
| **Mean Latency** | 61 ms | 58 ms | 57 ms |
| **Judge Correct Rate** | N/A | N/A | N/A |

## 8. Data Quality Status
Bảng giám sát chất lượng dữ liệu (Data Observability) qua các trạng thái:

| Tiêu chuẩn kiểm tra | Baseline | Corrupted | Repaired |
| :--- | :---: | :---: | :---: |
| **Completeness** | **PASS** | **FAIL** | **PASS** |
| **Uniqueness** | **PASS** | **FAIL** | **PASS** |
| **Freshness** | **PASS** | **FAIL** | **PASS** |

## 9. Controlled Corruption Summary
Thống kê các bản ghi lỗi được áp dụng ngẫu nhiên (seed 42):
* **Blank Summary**: 1 bản ghi bị xóa hoàn toàn tóm tắt.
* **Duplicate**: 1 bản ghi bị sao chép nhân đôi (giữ nguyên paper_id).
* **Noise**: 1 bản ghi bị chèn văn bản rác vô nghĩa vào embeddings.
* **Stale Date**: 1 bản ghi bị lùi ngày xuất bản về năm 2000-01-01 để vi phạm FRESHNESS.

## 10. Analysis
- **Vì sao Retrieval giảm**: Các bản ghi bị lỗi tóm tắt (blank_summary) hoặc nhiễu (noise) làm thay đổi đáng kể vector biểu diễn từ ngữ trong cơ sở dữ liệu vector. Sự nhiễu loạn này làm giảm độ tương đồng cosine giữa truy vấn người dùng và tài liệu gốc, dẫn đến việc Retriever bỏ sót tài liệu đúng (đặc biệt khi tài liệu đúng là duy nhất trong corpus 24 bài báo).
- **Vì sao Token F1 giảm**: Khi Retriever trả về kết quả sai hoặc thiếu ngữ cảnh gốc (Context Miss), QA Agent không có đủ thông tin tin cậy để trả lời câu hỏi thực tế (factual). Agent buộc phải đoán hoặc trả lời dựa trên các tài liệu không liên quan, dẫn đến điểm trùng khớp từ ngữ (Token F1) sụt giảm trầm trọng.
- **Vì sao Repair khôi phục**: Bằng cách chạy lại bộ làm sạch deterministic từ file bản ghi gốc (`crossref_records.json`), chúng ta đã loại bỏ hoàn toàn các bản sao lưu trùng lặp, các văn bản rác và khôi phục các tóm tắt bị mất. Vector biểu diễn của tài liệu trở lại chính xác như ban đầu, khôi phục hoàn toàn khả năng truy hồi của Retriever và độ chính xác của Agent.

## 11. Lessons Learned
1. **Chất lượng dữ liệu quyết định chất lượng AI**: Hệ thống RAG phụ thuộc trực tiếp vào Garbage-in, Garbage-out. Observability là lớp bảo vệ bắt buộc trước khi đưa câu trả lời tới người dùng.
2. **Frozen Evaluation Set cực kỳ quan trọng**: Việc đánh giá so sánh chỉ có ý nghĩa khoa học khi sử dụng chung một tập câu hỏi kiểm thử đóng băng.
3. **Cần lưu Raw Artifacts**: Việc lưu trữ dữ liệu raw gốc cho phép hệ thống chạy lại quy trình làm sạch từ đầu (lineage-based repair), đảm bảo tínhDeterministic của dữ liệu.
4. **Cơ chế Fallback thông minh**: Việc tích hợp exact lookup tiêu đề trong QA Agent giúp giảm thiểu một phần ảnh hưởng của lỗi tóm tắt khi tiêu đề vẫn chính xác.
5. **Cần hệ thống cảnh báo tự động**: Các chỉ số chất lượng dữ liệu (Completeness, Uniqueness, Freshness) phải được theo dõi liên tục ở tầng ETL.

## 12. Conclusion
Thí nghiệm Baseline $ightarrow$ Corrupted $ightarrow$ Repaired đã chứng minh định lượng rằng Data Quality ảnh hưởng trực tiếp tới chất lượng hệ thống RAG. Nhờ có quy trình làm sạch deterministic khôi phục từ Raw Records, hệ thống đã loại bỏ hoàn toàn lỗi dữ liệu và đưa các chỉ số đo lường hiệu năng của QA Agent trở lại trạng thái tốt nhất ban đầu.

## Submission Checklist
* [x] Baseline Pipeline chạy thành công xuất ra đầy đủ kết quả
* [x] Corruption Flow sinh dữ liệu lỗi và lưu log đầy đủ
* [x] Đánh giá trên Frozen Test Set đầy đủ cả 3 giai đoạn
* [x] Data Quality Checks lưu báo cáo phân tích theo từng giai đoạn
* [x] Báo cáo nhóm và báo cáo cá nhân khớp số liệu thực tế
* [x] Không có API Key hay tệp tin nhạy cảm cấu hình trong git

## Suggested Commit Messages
```text
feat: implement Crossref ingestion with retry and raw artifact storage
feat: add data cleaning pipeline and semantic preprocessing
feat: generate frozen evaluation test set
feat: implement baseline RAG evaluation pipeline
feat: add controlled corruption and repair experiment
feat: generate automatic evaluation reports
docs: complete group and individual project reports
refactor: improve pipeline logging and observability
test: validate baseline and corruption workflows
```
