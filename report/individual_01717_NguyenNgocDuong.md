# Individual Report - Nguyen Ngoc Duong

## 1. Student Information
* **Full Name**: Nguyễn Ngọc Dương
* **Student ID**: 01717

## 2. Owned Components
Phụ trách thiết kế và phát triển các thành phần sau:
* **Baseline Pipeline Orchestration**: Điều phối quy trình RAG pha dữ liệu sạch.
* **Controlled Corruption Flow**: Áp dụng lỗi dữ liệu ngẫu nhiên có kiểm soát và seed 42.
* **Lineage-based Repair Flow**: Khôi phục dữ liệu từ nguồn gốc thô.
* **Comparison Reporting**: Sinh báo cáo markdown so sánh kết quả tự động.

## 3. Technical Contributions
* Phát triển luồng điều phối chính trong [`phase1.py`](src/pipelines/phase1.py) và [`corruption_flow.py`](src/pipelines/corruption_flow.py).
* Cài đặt script entrypoint [`run_phase1.py`](script/run_phase1.py) và [`run_corruption_flow.py`](script/run_corruption_flow.py).
* Hỗ trợ cờ `--force` cho phép dọn sạch hoàn toàn các bản lưu cũ để bảo đảm thí nghiệm chạy lại đồng nhất.
* Thiết lập báo cáo so sánh tự động so sánh hiệu năng các pha trong [`reporting.py`](src/observability/reporting.py).

## 4. Evidence
* Module mã nguồn: [`phase1.py`](src/pipelines/phase1.py), [`corruption_flow.py`](src/pipelines/corruption_flow.py), [`run_phase1.py`](script/run_phase1.py), [`run_corruption_flow.py`](script/run_corruption_flow.py)
* Báo cáo so sánh: [`corruption_report.md`](data/reports/corruption_report.md)

## 5. Challenges
* Gặp khó khăn khi quản lý các tệp tin cấu hình và tài nguyên ChromaDB index khác nhau giữa các pha. Đã khắc phục bằng cách ánh xạ rõ ràng từng bộ sưu tập (baseline, corrupted, repaired) trong manifest JSON tương ứng.

## 6. Lessons Learned
* Idempotency (tính lũy đẳng) của pipeline giúp đảm bảo tính tin cậy của kết quả thực nghiệm.
* Việc chạy thử nghiệm nhiều pha tự động giúp phát hiện ra các góc khuất dữ liệu bị lỗi nhanh hơn.

## 7. Conclusion
Pipeline thí nghiệm chạy end-to-end trơn tru, giúp hoàn thành và minh họa rõ nét tiến trình Baseline $
ightarrow$ Corrupted $
ightarrow$ Repaired.
