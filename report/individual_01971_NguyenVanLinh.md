# Individual Report - Nguyen Van Linh

## 1. Student Information
* **Full Name**: Nguyễn Văn Linh
* **Student ID**: 2A202601971

## 2. Owned Components
Phụ trách thiết kế và phát triển các thành phần sau:
* **RAG QA Agent**: Logic xử lý câu hỏi, truy xuất ngữ cảnh và trả lời.
* **Frozen Evaluation Set Generation**: Sinh bộ câu hỏi đóng băng từ dữ liệu sạch.
* **Performance Metrics Calculation**: Đo lường Retrieval Hit Rate và F1 Token score.
* **LLM Judge & Observability Reports**: Cấu hình giám sát LLM Judge.

## 3. Technical Contributions
* Triển khai hàm sinh câu hỏi `build_test_set` trong [`testset.py`](src/evaluation/testset.py) với 5 loại câu hỏi factual.
* Triển khai QA Agent trả lời câu hỏi factual trong [`qa.py`](src/retrieval/qa.py). Bổ sung exact lookup tiêu đề bằng regex khớp chính xác tiêu đề bài báo, tăng độ tin cậy khi tài liệu bị lỗi tóm tắt.
* Viết thuật toán tính `calculate_token_f1` đo lường sự tương đồng từ vựng và tích hợp LLMJudge đánh giá chất lượng tự động.

## 4. Evidence
* Module mã nguồn: [`qa.py`](src/retrieval/qa.py), [`testset.py`](src/evaluation/testset.py), [`metrics.py`](src/evaluation/metrics.py)
* Dữ liệu sinh ra: [`test_set.json`](data/eval/test_set.json), các tệp metrics trong [`results/`](data/results/).

## 5. Challenges
* QA Agent trả về kết quả rỗng cho câu hỏi tiếng Việt do bộ lọc so khớp chuỗi bằng tiếng Anh. Đã khắc phục bằng cách hỗ trợ từ khóa tiếng Việt đa dạng như "tác giả", "tạp chí", "lĩnh vực" trong hàm trích xuất câu trả lời.

## 6. Lessons Learned
* Bộ kiểm thử đóng băng (Frozen Evaluation Set) đóng vai trò quyết định để định lượng hiệu năng cải tiến.
* Tối ưu hóa câu lệnh prompt và so khớp thông tin từ metadata giúp RAG Agent hoạt động chính xác và có khả năng chống chịu lỗi dữ liệu cao hơn.

## 7. Conclusion
Bộ câu hỏi kiểm thử và RAG Agent đã phối hợp hoạt động hiệu quả, đem lại điểm F1 ấn tượng đạt **0.9087** trên dữ liệu sạch.
