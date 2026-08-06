# Bước 5 — Tạo evaluation set

File đã hoàn thành: `src/evaluation/testset.py`
Ngày chạy: 2026-08-06 · Corpus 24 papers → **48 samples** · Artifact: `data/eval/test_set.json` (23 KB)

---

## 1. Phương pháp tạo câu hỏi

**Template-based (rule-based), không dùng LLM.**

Bốn template cố định, mỗi template điền title của paper vào:

| `question_type` | Template | Ground truth lấy từ |
|---|---|---|
| `summary` | `What is the main contribution of the paper '{title}'?` | `first_sentence(summary)` |
| `authors` | `Who authored the paper '{title}'?` | `authors_joined` |
| `date` | `When was the paper '{title}' published?` | `published` |
| `categories` | `What categories are assigned to the paper '{title}'?` | `categories_joined` |

### Tại sao template thay vì LLM-generated?

Đây không phải lựa chọn cho tiện — với bài lab này, template là phương pháp **đúng**:

1. **Ground truth phải tuyệt đối chính xác.** Toàn bộ mục tiêu của lab là đo xem *chất lượng dữ liệu* ảnh hưởng thế nào tới chất lượng agent. Nếu ground truth do LLM sinh ra, nó mang theo nhiễu và ảo giác của chính LLM đó — khi metric tụt ở pha 2, không thể phân biệt được là do corruption hay do ground truth vốn đã sai.

2. **Phải tái lập được.** Bộ câu hỏi được dùng lại **y hệt** cho cả ba trạng thái baseline / corrupted / repaired. Chỉ khi test set bất biến thì chênh lệch metric mới quy được về nguyên nhân dữ liệu. LLM sinh câu hỏi mỗi lần một khác, kể cả `temperature=0`.

3. **Ground truth phải khớp chính xác cơ chế trả lời.** Đây là ràng buộc nặng nhất, xem mục 2 bên dưới.

4. **Không tốn API call, không cần key.** Bước 5 chạy được kể cả khi chưa cấu hình LLM provider.

Đánh đổi phải chấp nhận: câu hỏi có cấu trúc lặp lại, không đa dạng ngôn ngữ như người thật hỏi. Với mục tiêu đo *tác động của corruption* thì không sao — chỉ cần bộ đo ổn định và có độ nhạy, không cần bộ đo giống người dùng thật.

### Ràng buộc bắt buộc từ code có sẵn

Template không thể đặt tùy ý. `retrieval/qa.py::_extract_answer` ([qa.py:20-29](../src/retrieval/qa.py#L20-L29)) chọn câu trả lời bằng **so khớp chuỗi trên câu hỏi**:

```python
if "who authored" in lowered or "list the authors" in lowered:  → authors_joined
if "when was" / "publication date" / "published on" in lowered: → published
if "what categories" in lowered:                                → categories_joined
mặc định:                                                       → first_sentence(summary)
```

Nên câu hỏi loại `authors` **bắt buộc** phải chứa đúng chuỗi `"who authored"` hoặc `"list the authors"`. Một câu hỏi tự nhiên hơn như *"Which researchers wrote this paper?"* sẽ rơi xuống nhánh mặc định, trả về câu đầu của abstract, và không bao giờ khớp ground truth — `token_f1` tụt vì template sai chứ không phải vì hệ thống kém.

Để lỗi này không bao giờ lọt, module tự kiểm tra bằng hàm `_route_of()` — bản sao chính xác logic route của `qa.py`. Mỗi sample sinh ra đều được kiểm tra `_route_of(question) == question_type`, lệch thì bị loại và ghi log. Nếu sau này ai đó sửa template, sample sai sẽ bị chặn ngay thay vì âm thầm kéo metric xuống.

### Title đặt trong dấu nháy đơn

`answer_question` ([qa.py:33](../src/retrieval/qa.py#L33)) có regex `r"'([^']+)'"`: nếu câu hỏi chứa một cụm trong dấu nháy đơn, cụm đó được đem đi lookup exact theo `paper_id` hoặc title, và document tìm được sẽ được đẩy lên đầu danh sách retrieved.

Vì vậy mọi template đều bọc title trong `'...'`. Điều này khiến `retrieval_hit_rate` ở baseline phản ánh đúng "corpus có chứa document này không", và ở pha 2 nó trở thành tín hiệu trực tiếp: khi corruption **xóa** record hoặc **cắt cụt title**, lookup exact thất bại ngay lập tức.

Đã kiểm tra: **48/48** câu hỏi có phần trong dấu nháy trùng khớp chính xác với một title trong corpus. (Corpus hiện tại không có title nào chứa dấu nháy đơn — nếu có, regex sẽ cắt sai và sample đó mất phần thưởng lookup, tuy vẫn còn semantic search.)

---

## 2. Các loại `question_type`

Bốn loại, chọn để cover **bốn trường dữ liệu khác nhau** — nhờ đó mỗi kiểu corruption ở pha 2 đều có ít nhất một loại câu hỏi bắt được:

| `question_type` | Trường bị đo | Kiểu corruption mà nó bắt được |
|---|---|---|
| `summary` | `summary` | Blank summary, inject noise vào text |
| `authors` | `authors_joined` | Drop record, duplicate |
| `date` | `published` | Làm ngày cũ đi (dịch ngày) |
| `categories` | `categories_joined` | Drop record, duplicate |

Ánh xạ này là lý do phải có đủ cả bốn loại. Nếu chỉ có câu hỏi summary, corruption làm hỏng ngày tháng sẽ đi qua mà không ai thấy trong metric.

### Phân bổ

| `question_type` | Số sample | Tỉ lệ |
|---|---|---|
| `summary` | **24** | 50% |
| `authors` | 8 | 17% |
| `date` | 8 | 17% |
| `categories` | 8 | 17% |
| **Tổng** | **48** | 100% |

**Quy tắc phân bổ** (`_types_for_row`): mỗi paper luôn nhận **một câu hỏi `summary`**, cộng thêm **một câu hỏi thứ hai xoay vòng** qua `authors → date → categories` theo vị trí dòng.

Vì sao `summary` chiếm gấp ba loại kia:

- `summary` là trường **dài nhất và giàu thông tin nhất** (trung bình 1.724 ký tự) — cũng là trường dễ hỏng nhất và là mục tiêu của hai trong sáu kiểu corruption.
- Ba loại còn lại có ground truth ngắn và gần như nhị phân: hoặc lấy đúng document (điểm ~1.0) hoặc sai document (điểm ~0.0). Thêm nhiều sample loại này chỉ làm metric thêm nhiễu chứ không thêm thông tin.
- `summary` cho tín hiệu **liên tục**: nhiễu chèn vào text làm `token_f1` giảm dần dần thay vì rơi thẳng xuống 0, nên biểu đồ so sánh ba trạng thái ở pha 2 sẽ mượt và đọc được.

Xoay vòng theo vị trí dòng (dataframe đã sort theo `published` giảm dần) đảm bảo ba loại kia trải đều trên trục thời gian, không dồn hết vào nhóm paper mới hay paper cũ.

---

## 3. Số lượng sample

**48 samples** trên corpus 24 papers = 2 câu hỏi/paper, **phủ 24/24 papers**.

### Vì sao phủ toàn bộ corpus

Đây là điểm quan trọng nhất trong thiết kế. Corruption ở pha 2 chỉ tác động lên **một tập con** các record (drop vài record mới nhất, blank vài summary, duplicate vài dòng). Nếu evaluation set chỉ lấy mẫu vài paper đại diện, rất có thể corruption rơi đúng vào những paper *không* nằm trong test set — metric sẽ gần như đứng yên và cả bài lab mất đi kết luận chính.

Phủ 100% corpus đảm bảo **mọi record bị làm hỏng đều nằm trong tầm đo**.

### Vì sao 2 câu/paper chứ không phải 4

Số sample quyết định thẳng chi phí evaluation. `metrics.py::_judge_answer` gọi LLM **một lần cho mỗi sample**, và evaluation chạy **ba lần** (baseline, corrupted, repaired):

| Cấu hình | Samples | Tổng LLM call cho cả 3 lần chạy |
|---|---|---|
| 1 câu/paper | 24 | 72 |
| **2 câu/paper (mặc định)** | **48** | **144** |
| 4 câu/paper | 96 | 288 |

48 là điểm cân bằng: đủ phủ toàn bộ corpus, mỗi sample chiếm ~2% metric nên chênh lệch ở pha 2 đọc được rõ, mà vẫn nằm trong hạn mức free tier của Gemini.

Tham số `questions_per_paper` để mở, mặc định `2`. Đặt `4` sẽ sinh đủ cả bốn loại cho mọi paper — đã kiểm tra: 96 samples, cân bằng tuyệt đối 24/24/24/24.

Ngoài ra `metrics.py` có sẵn cơ chế fallback: nếu LLM judge lỗi hoặc chưa có API key, nó tự chuyển sang heuristic dựa trên `token_f1` ([metrics.py:64-70](../src/evaluation/metrics.py#L64-L70)). Nên evaluation vẫn chạy được ở chế độ không tốn API call, chỉ mất chỉ số `judge_accuracy` do LLM chấm.

---

## 4. Schema mỗi sample

Đúng 5 trường mà `metrics.py::evaluate_pipeline` đọc ([metrics.py:113-131](../src/evaluation/metrics.py#L113-L131)):

```json
{
  "id": "q002",
  "question_type": "authors",
  "question": "Who authored the paper 'SafeRAG: A Large-Language-Model-Based Multistage Retrieval-Augmented Framework for Oil and Gas Safety Report Generation'?",
  "ground_truth": "Qianwen Cao, Chiyu Zhang, Junxiong Ning, Gongru Li",
  "ground_truth_doc_ids": ["10.2118/234689-pa"]
}
```

| Trường | Vai trò |
|---|---|
| `id` | Định danh chạy số `q001`…`q048`, để đối chiếu giữa ba file answers |
| `question_type` | Nhãn để bóc tách metric theo loại khi phân tích |
| `question` | Input đưa vào `answer_question` |
| `ground_truth` | Chuẩn so sánh cho `_token_f1` và LLM judge |
| `ground_truth_doc_ids` | Danh sách DOI dùng tính `retrieval_hit_rate` |

`ground_truth_doc_ids` luôn chứa đúng một DOI: mọi câu hỏi đều gắn với một paper cụ thể nhờ title trong dấu nháy. `retrieval_hit` đúng khi bất kỳ document nào trong top-k (`top_k=4`) trùng DOI đó.

---

## 5. Kiểm tra chất lượng test set

### Oracle check — phần quan trọng nhất

Kiểm tra này mô phỏng lại chính xác `qa.py::_extract_answer`, chạy trên **đúng document đích** của từng sample, rồi so kết quả với `ground_truth` bằng chính hàm `_token_f1` của `metrics.py`:

```
mean_token_f1 = 1.0000   (kỳ vọng: 1.0)
sample không đạt f1 = 1.0: không có
```

Ý nghĩa: **nếu retrieval lấy đúng document, câu trả lời khớp ground truth tuyệt đối.** Trần điểm của test set là 1.0, nên mọi sụt giảm quan sát được ở pha 2 đều quy được về dữ liệu chứ không phải về sai lệch có sẵn của bộ đo. Không có kiểm tra này thì baseline sẽ có một mức "thất thoát nền" không rõ nguồn gốc, làm nhiễu toàn bộ phần so sánh.

### Toàn bộ kết quả kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Số sample sinh ra | 48 |
| Papers được phủ | **24 / 24** |
| Đủ 5 trường schema | Đạt |
| `id` duy nhất | Đạt |
| `ground_truth` rỗng | 0 |
| `ground_truth_doc_ids` tồn tại trong corpus | 48/48 |
| `_route_of(question) == question_type` | 48/48 |
| Title lookup exact hoạt động | 48/48 |
| **Oracle `mean_token_f1`** | **1.0000** |
| Cân bằng khi `questions_per_paper=4` | 96 samples, 24/24/24/24 |

Test chạy bằng venv tạm (pandas 3.0.5) do `uv sync` chưa xong, nạp thẳng `testset.py` để tránh import chain qua `evaluation/__init__.py`. Cần chạy lại trong `.venv` chính thức để xác nhận.

---

## 6. Điểm cần lưu ý cho các bước sau

1. **Test set phải sinh một lần rồi tái sử dụng.** `Settings` có cờ `refresh_test_set`; pipeline ở bước 9 chỉ nên tạo mới khi cờ bật, còn lại load từ `data/eval/test_set.json`. Nếu pha 2 sinh lại test set từ dữ liệu đã bị corrupt thì so sánh baseline/corrupted mất hoàn toàn ý nghĩa — ground truth sẽ bị làm hỏng cùng với dữ liệu.

2. **Baseline nên đạt gần trần.** Với oracle f1 = 1.0 và mỗi câu hỏi có title đặt trong dấu nháy, `retrieval_hit_rate` ở baseline được kỳ vọng rất cao (~1.0) và `mean_token_f1` cũng vậy. Nếu chạy thật mà thấp hơn nhiều, nghi vấn nằm ở bước embedding/index chứ không phải ở test set.

3. **Câu hỏi loại `categories` khá dễ.** Ground truth là tên tạp chí (kế thừa hạn chế `subject` rỗng của Crossref từ bước 3), mỗi paper chỉ có đúng một category. Loại này chủ yếu đo retrieval chứ gần như không đo được khả năng hiểu.

4. **Nếu đổi template, phải chạy lại oracle check.** Sửa một chữ trong template có thể làm câu hỏi đổi nhánh route và kéo metric xuống mà không có lỗi nào được ném ra. `_route_of` chặn được trường hợp lệch nhánh, nhưng oracle check mới là thứ xác nhận ground truth vẫn khớp.
