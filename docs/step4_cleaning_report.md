# Bước 4 — Làm sạch dữ liệu

File đã hoàn thành: `src/ingestion/cleaning.py`
Ngày chạy: 2026-08-06 · Input: 24 raw records → Output: 24 clean rows

---

## 1. Tiêu chí loại bỏ record không hợp lệ

Record bị loại nếu vi phạm **bất kỳ** điều kiện nào dưới đây. Thứ tự kiểm tra: làm sạch trước, lọc sau — để một record chỉ "bẩn" chứ không "hỏng" vẫn được giữ lại.

| # | Tiêu chí | Ngưỡng | Lý do |
|---|---|---|---|
| 1 | Thiếu `paper_id` | rỗng sau khi làm sạch | DOI là khóa chính, không có thì không tính được `retrieval_hit_rate` |
| 2 | Title quá ngắn | `< 10` ký tự | Title là neo chính cho câu hỏi exact-lookup ở bước 5 |
| 3 | Summary quá ngắn | `< 120` ký tự | Summary vừa là input embedding vừa là ground truth câu hỏi summary |
| 4 | Không có tác giả | `len(authors) == 0` | Câu hỏi loại `authors` sẽ có ground truth rỗng → sample hỏng |
| 5 | Không có category | `len(categories) == 0` | Tương tự với câu hỏi loại `categories` |
| 6 | Ngày xuất bản không parse được | không khớp `YYYY-MM-DD` | Không tính được `age_days` |
| 7 | Ngày xuất bản ở tương lai | `published > run_date` | `age_days` sẽ âm, phá freshness report |
| 8 | Quá cũ | `age_days > 3650` (10 năm) | Bắt lỗi ngày rác kiểu `1900-01-01` |
| 9 | Trùng `paper_id` | đã gặp trước đó | Duplicate làm lệch retrieval và inflate row count |
| 10 | Trùng title (không phân biệt hoa thường) | đã gặp trước đó | Cùng paper nộp 2 DOI (preprint + bản chính) |

**Tại sao 4 và 5 lại là điều kiện loại bỏ, không phải cảnh báo?**
Ba loại câu hỏi trong evaluation set lấy ground truth trực tiếp từ `authors_joined`, `categories_joined`, `summary` ([qa.py:20-29](../src/retrieval/qa.py#L20-L29)). Một record thiếu tác giả mà lọt vào corpus sẽ sinh ra sample có ground truth rỗng, và `_token_f1` trả về `0.0` cho mọi answer — metric tụt vì lỗi dữ liệu chứ không phải vì retrieval kém. Loại sớm ở đây sạch hơn là xử lý ngoại lệ ở bước 5.

**Ngưỡng 120 ký tự cho summary** chọn thấp hơn nhiều so với thực tế (ngắn nhất trong corpus là 826 ký tự) — mục đích là bắt trường hợp abstract rỗng/cụt, không phải cắt bớt corpus. Ngưỡng này còn có vai trò ở pha 2: corruption "blank summary" sẽ làm record rơi xuống dưới ngưỡng và data quality check phải phát hiện được.

**Kết quả thực tế:** 24/24 record đi qua toàn bộ 10 tiêu chí. Đó là điều mong đợi, vì bước 3 đã lọc sẵn ở tầng API (`has-abstract:true`) và tầng parse. Cleaning ở đây đóng vai trò lưới an toàn thứ hai — quan trọng vì pha 2 sẽ chạy lại chính hàm này trên dữ liệu đã bị cố ý làm hỏng.

Đã kiểm tra từng tiêu chí bằng record dựng tay: cả 8 trường hợp lỗi đều bị loại đúng, và 2 record cùng `paper_id` chỉ còn lại 1 dòng.

---

## 2. Quy tắc chuẩn hóa theo từng trường

### Bộ làm sạch dùng chung (`_clean_text`)

Áp dụng cho mọi trường text, theo đúng thứ tự:

1. **Strip markup** — bỏ mọi tag `<...>` còn sót (JATS: `<jats:p>`, `<scp>`, `<i>`)
2. **Unescape entity** — `&amp;` → `&`, `&lt;` → `<`
3. **Gom whitespace** — nhiều khoảng trắng/xuống dòng/tab → một dấu cách
4. **Sửa khoảng trắng trước dấu câu** — `"RAG : A Study"` → `"RAG: A Study"`

Thứ tự strip-trước-unescape là có chủ ý: nếu unescape trước, chuỗi `&lt;b&gt;` sẽ biến thành tag thật rồi bị bước strip xóa mất nội dung.

Bước 3 đã chạy bộ này rồi, nhưng cleaning **cố tình lặp lại** — vì `build_clean_dataframe` còn được gọi lần nữa trong pha 2 trên dữ liệu đã bị inject noise, lúc đó không có gì đảm bảo input đã sạch.

### Từng trường cụ thể

| Trường | Quy tắc riêng |
|---|---|
| `title` | `_clean_text` + cắt dấu câu thừa ở hai đầu (`-`, `–`, `:`, `;`, `,`, `.`) |
| `summary` | `_clean_text` + **bỏ nhãn section ở đầu** (xem dưới) |
| `authors` | `_clean_text` từng phần tử → bỏ phần tử rỗng → khử trùng lặp **không phân biệt hoa thường** (`"A B"`, `"a b"`, `" A B "` → còn 1) → giữ nguyên thứ tự gốc (thứ tự tác giả có ý nghĩa học thuật) |
| `categories` | Cùng quy tắc với `authors` |
| `primary_category` | Làm sạch; nếu rỗng thì lấy `categories[0]` |
| `published` / `updated` | Parse sang `date` rồi format lại ISO — đảm bảo output luôn hợp lệ; `updated` rỗng thì fallback về `published` |
| `abs_url` | Làm sạch; rỗng thì dựng `https://doi.org/{paper_id}` |
| `pdf_url` | Chỉ làm sạch, **cho phép rỗng** (16/24 record không có link PDF, trường này không tham gia embedding hay evaluation) |
| `comment` | Chỉ làm sạch |

### Bỏ nhãn section ở đầu summary

Crossref lưu abstract có cấu trúc bằng `<jats:title>`, sau khi strip tag thì nhãn dính liền vào text:

```
"BACKGROUND There is evidence of rapid adoption..."
"Summary In high-risk industrial settings..."
"Background. Insurance penetration in Kenya..."
```

Có **4/24 record** dính lỗi này. Việc xử lý là bắt buộc chứ không phải làm đẹp: `first_sentence(summary)` chính là ground truth cho câu hỏi loại summary, nên nhãn thừa sẽ nằm ngay đầu mọi câu trả lời chuẩn.

Regex bỏ nhãn dẫn đầu — `abstract | summary | background | introduction | objective(s) | purpose | aim(s) | context | highlights` — kèm dấu câu theo sau, lặp tối đa 3 lần để xử lý trường hợp chồng nhãn kiểu `"Abstract Background The..."`. Sau xử lý: **0/24** summary còn nhãn.

### Cột `text_for_embedding`

```
Title: {title}
Authors: {authors_joined}
Categories: {categories_joined}
Published: {published}
Summary: {summary}
```

Thứ tự các dòng **không tùy tiện**. `all-MiniLM-L6-v2` có cửa sổ 256 word-piece (~180 từ), trong khi summary trung bình đã 1.724 ký tự — phần đuôi chắc chắn bị cắt. Vì vậy title, tác giả, category và ngày phải nằm trước để luôn nằm trong cửa sổ. Điều này khớp trực tiếp với 4 loại câu hỏi ở bước 5: câu hỏi về tác giả/ngày/category sẽ retrieve được đúng document ngay cả khi phần summary bị cắt.

Đưa cả metadata vào text embedding (chứ không chỉ summary) cũng làm bước corruption có ý nghĩa hơn: khi pha 2 làm hỏng title hoặc ngày, vector embedding thay đổi theo và `retrieval_hit_rate` phản ứng — nếu chỉ embed summary thì corrupt title sẽ không tác động gì tới retrieval.

---

## 3. Cách tính `age_days`

```python
run_day  = run_date.date()                                    # UTC, do pipeline truyền vào
published = datetime.strptime(record.published, "%Y-%m-%d").date()
age_days  = (run_day - published).days                        # số nguyên, đơn vị ngày
```

Các quyết định thiết kế:

- **`run_date` là tham số, không phải `datetime.now()` bên trong hàm.** Nhờ vậy `build_clean_dataframe` là hàm thuần túy — cùng input cho cùng output, test lặp lại được, và pha 2 có thể tái tạo lại đúng dataset cũ.
- **Hàm nhận cả `datetime` lẫn `date`** (`_as_date`), tránh vỡ khi pipeline truyền `now_utc()` có timezone.
- **So sánh ở cấp `date`, không phải `datetime`.** Crossref chỉ cho độ chính xác tới ngày (thậm chí nhiều record chỉ có năm — bước 3 đã điền `01-01`), nên giữ phần giờ chỉ tạo cảm giác chính xác giả.
- **Không có giá trị âm.** Đã chặn bằng tiêu chí #7 thay vì clamp về 0 — clamp sẽ giấu mất lỗi dữ liệu, mà phát hiện lỗi dữ liệu chính là mục tiêu của bài lab.

### Liên hệ với freshness

`freshness_threshold_days = 180` trong `core/config.py`, và filter Crossref ở bước 3 dùng đúng con số đó làm cận dưới. Nên baseline **theo thiết kế** phải có toàn bộ record với `age_days ≤ 180`:

| | Giá trị |
|---|---|
| `age_days` nhỏ nhất | 5 |
| `age_days` lớn nhất | **175** |
| Số dòng `age_days > 180` | **0** |
| Số dòng `age_days < 0` | 0 |

175 < 180 với biên rất mỏng — đúng như mong muốn. Baseline là "fresh" nhưng không dư dả, nên khi pha 2 đẩy ngày lùi lại, `stale_rows` sẽ tăng ngay và freshness report chuyển trạng thái rõ ràng. Nếu corpus toàn paper 5 ngày tuổi thì corruption phải đẩy lùi rất xa mới thấy tín hiệu.

---

## 4. Schema output

18 cột, cố định qua hằng `CLEAN_COLUMNS`:

| Nhóm | Cột |
|---|---|
| Định danh & nội dung | `paper_id`, `title`, `summary` |
| Trường dạng list | `authors`, `categories`, `primary_category` |
| Ngày | `published`, `updated` |
| Link & ghi chú | `abs_url`, `pdf_url`, `comment` |
| Trường phái sinh cho retrieval | `authors_joined`, `categories_joined` |
| Trường phái sinh cho quality check | `summary_chars`, `title_chars`, `author_count`, `age_days` |
| Input embedding | `text_for_embedding` |

9 cột đầu tiên mà `retrieval/index.py` đọc (`paper_id`, `title`, `text_for_embedding`, `published`, `authors_joined`, `categories_joined`, `summary`, `abs_url`, `pdf_url`) đều có mặt — đã assert trong test.

Dataframe được **sort theo `published` giảm dần, tie-break bằng `paper_id`**, rồi reset index. Thứ tự cố định là cần thiết để so sánh baseline với repaired ở pha 2 mà không bị nhiễu bởi thứ tự dòng.

Ba cột `summary_chars`, `title_chars`, `author_count` tính sẵn ở đây thay vì để `observability/quality.py` tự tính lại — quality check chỉ nên **đọc và so ngưỡng**, và các cột này cũng nằm luôn trong CSV để kiểm tra bằng mắt.

### Lưu ý về CSV vs JSON

`authors` và `categories` là list Python. Khi ghi ra hai định dạng:

| Định dạng | Kiểu của `authors` khi đọc lại |
|---|---|
| `papers_clean.json` | `list` — nguyên vẹn |
| `papers_clean.csv` | `str` — `"['A B', 'C D']"` |

Đây là hạn chế cố hữu của CSV. Vì vậy **pipeline ở bước 9 nên đọc lại từ JSON**, còn CSV để cho người xem. Hai cột `authors_joined` / `categories_joined` an toàn với cả hai định dạng, và đó cũng chính là hai cột mà index và qa thực sự dùng.

---

## 5. Kết quả kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Số dòng | 24 raw → 24 clean |
| Đúng `CLEAN_COLUMNS` | Đạt |
| Đủ cột theo hợp đồng của `index.py` | Đạt |
| Giá trị null | 0 |
| Chuỗi rỗng ở các cột bắt buộc | 0 |
| `paper_id` / title trùng lặp | 0 / 0 |
| `age_days` âm | 0 |
| Summary còn nhãn section | 0 |
| `first_sentence(summary)` quá ngắn (< 20 ký tự) | 0 |
| Sort giảm dần theo `published` | Đạt |
| 10 test case record lỗi | Loại đúng cả 10 |

**Cách chạy test:** `uv sync` chưa xong nên test chạy bằng venv tạm với pandas 3.0.5 và stub `dotenv`. Logic cleaning là thuần pandas cơ bản (`DataFrame`, `sort_values`, `reset_index`) nên không phụ thuộc phiên bản, nhưng vẫn cần chạy lại trong `.venv` chính thức để xác nhận.

---

## 6. Điểm cần lưu ý cho các bước sau

1. **Đọc clean data từ JSON, không phải CSV**, nếu cần cột `authors`/`categories` dạng list.

2. **`categories` vẫn là tên tạp chí** (kế thừa từ bước 3 — Crossref bỏ trống field `subject`). Cleaning không sửa được điều này vì đây là hạn chế của nguồn. Câu hỏi `what categories` ở bước 5 sẽ có ground truth là tên tạp chí, và vì mỗi record có đúng 1 category nên loại câu hỏi này khá dễ.

3. **Biên freshness rất mỏng** (max 175 / ngưỡng 180). Nếu chạy lại pipeline vào ngày khác, `from-pub-date` dịch theo nên biên vẫn giữ — nhưng nếu ai đó dùng lại snapshot raw cũ sau vài tuần thì sẽ có record vượt ngưỡng và freshness báo `stale` ngay ở baseline. Đây là hành vi đúng, không phải bug.

4. **Cleaning được thiết kế để chạy hai lần.** Toàn bộ quy tắc chuẩn hóa là idempotent, và các tiêu chí lọc chính là thứ mà corruption ở pha 2 nhắm vào phá vỡ: summary bị blank sẽ chạm tiêu chí #3, duplicate chạm #9, ngày bị đẩy lùi làm `age_days` vượt ngưỡng freshness.
