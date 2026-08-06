# Bước 3 — Load raw data từ source (Crossref)

File đã hoàn thành: `src/ingestion/crossref.py`
Ngày chạy: 2026-08-06

---

## 1. Source nào đang được dùng?

**Crossref REST API** — `https://api.crossref.org/works`

Crossref là registry DOI lớn nhất cho công bố học thuật. API công khai, **không cần API key**, trả về metadata: DOI, title, abstract, danh sách tác giả, subject, ngày xuất bản, URL và link full-text.

Vài đặc điểm của nguồn này ảnh hưởng trực tiếp tới cách parse:

| Đặc điểm | Hệ quả khi ingest |
|---|---|
| `abstract` là **JATS XML** (`<jats:p>…</jats:p>`) | Phải strip tag + unescape entity trước khi dùng |
| `title` cũng có thể chứa markup (`<scp>`, `<i>`, `<sub>`) | Áp dụng cùng bộ làm sạch như abstract |
| Ngày ở dạng `date-parts` (`[[2026, 6, 15]]`), có thể thiếu tháng/ngày | Cần chuẩn hóa về ISO `YYYY-MM-DD`, thiếu thì mặc định `01` |
| Nhiều field ngày khác nhau: `published`, `issued`, `published-online`, `published-print`, `created` | Phải chọn theo thứ tự ưu tiên |
| `subject` gần như luôn rỗng ở record hiện đại | Cần fallback để `categories` không trống |
| Có record "forthcoming" ngày xuất bản ở **tương lai** | Phải loại bỏ, nếu không `age_days` sẽ âm |
| Không phải record nào cũng có link PDF | `pdf_url` được phép rỗng |

**Chính sách gọi API:** gửi header `User-Agent` mô tả ứng dụng; nếu đặt biến môi trường `CROSSREF_MAILTO` thì thêm `mailto:` để vào *polite pool* của Crossref (được ưu tiên rate limit).

---

## 2. Query/filter là gì?

Tham số lấy từ `Settings` trong `src/core/config.py`:

```python
query   = "agentic retrieval augmented generation large language model"
filter  = "from-pub-date:<hôm nay - 180 ngày>,has-abstract:true"
rows    = 24          # settings.max_results
sort    = "relevance"
order   = "desc"
```

Cụ thể cho lần chạy 2026-08-06: `filter = from-pub-date:2026-02-07,has-abstract:true,until-pub-date:2026-08-06`

Giải thích từng phần:

- **`query`** — full-text search trên metadata. Xác định chủ đề corpus là agentic RAG / LLM.
- **`from-pub-date`** — chặn dưới 180 ngày, khớp với `freshness_threshold_days = 180`. Nhờ vậy baseline corpus mặc định là "fresh", và bước corruption (làm ngày cũ đi) mới tạo được khác biệt đo được.
- **`has-abstract:true`** — bắt buộc, vì `summary` là nguồn text chính cho embedding và cho ground truth của câu hỏi loại summary.
- **`rows=24`** — khớp `settings.max_results`.

### Hai điều chỉnh so với cấu hình gốc

Cả hai đều nằm trong `crossref.py`, **không sửa `config.py`**:

**a) Thêm `until-pub-date:<hôm nay>`** (hàm `_bounded_filter`)

`source_filter` gốc chỉ có chặn dưới. Crossref có record "forthcoming" với ngày xuất bản tương lai — lần chạy thử trả về paper ghi `2028-06-15`. Những record này làm `age_days` âm và khiến freshness report vô nghĩa. Có thêm một lớp bảo vệ thứ hai ở tầng parse: bỏ mọi record có `published > hôm nay`.

**b) `sort=relevance` thay vì `sort=issued`**

Đây là điều chỉnh quan trọng hơn. Ban đầu dùng `sort=issued&order=desc` với ý định lấy paper mới nhất, nhưng kết quả thực tế:

| | `sort=issued` | `sort=relevance` |
|---|---|---|
| Chủ đề | Lạc đề hoàn toàn (giáo dục tiểu học, HRI robot…) | 24/24 đúng về RAG / LLM / agentic AI |
| Khoảng ngày | Tất cả cùng một ngày (2026-08-06) | 2026-02-12 → 2026-08-01 |

Sort theo ngày khiến `query` chỉ còn tác dụng lọc thô, kết quả là 24 paper *mới nhất* chứ không phải *liên quan nhất*. Corpus lạc đề thì test set và mọi metric retrieval ở các bước sau đều mất ý nghĩa. Ngoài ra ngày trùng nhau hết cũng làm freshness report không có gì để phân biệt.

---

## 3. Record schema gồm những trường nào?

Dataclass `PaperRecord` — 11 trường (schema này do starter code định sẵn, không tự đặt):

| Trường | Kiểu | Nguồn Crossref | Ghi chú |
|---|---|---|---|
| `paper_id` | `str` | `DOI` | Khóa chính, hạ về chữ thường |
| `title` | `str` | `title[0]` | Đã strip markup |
| `summary` | `str` | `abstract` | JATS → plain text, bỏ nhãn "Abstract" ở đầu |
| `authors` | `list[str]` | `author[].given + family` | Fallback `author[].name`, khử trùng lặp |
| `categories` | `list[str]` | `subject` | Fallback: `container-title` → `type` |
| `primary_category` | `str` | `categories[0]` | |
| `published` | `str` | `published` → `issued` → `published-online` → `published-print` → `created` | ISO `YYYY-MM-DD` |
| `updated` | `str` | `deposited` → `indexed` → `created` | Fallback về `published` |
| `abs_url` | `str` | `URL` | Fallback `https://doi.org/{DOI}` |
| `pdf_url` | `str` | `link[]` có `content-type=application/pdf` | Được phép rỗng |
| `comment` | `str` | `type`, `container-title`, `publisher` | Ghép thành một chuỗi mô tả |

### Quy tắc loại bỏ record

Một record bị bỏ nếu: thiếu `DOI`, thiếu `title`, `abstract` rỗng sau khi làm sạch, không parse được ngày xuất bản, ngày xuất bản ở tương lai, hoặc DOI trùng với record đã nhận.

---

## 4. Ba hàm đã implement

| Hàm | Vai trò |
|---|---|
| `parse_crossref_payload(payload)` | Payload thô → `list[PaperRecord]`, thuần túy (không I/O, không network) nên dễ test |
| `fetch_source_records(settings)` | Gọi API → lưu raw response → parse → lưu raw records |
| `load_raw_records(path)` | Đọc snapshot JSON → dựng lại `PaperRecord` |

**Retry** (`_request_with_retry`): tối đa 5 lần cho các status `429, 500, 502, 503, 504`, backoff mũ 1→2→4→8→16 giây, **ưu tiên header `Retry-After`** nếu server có gửi. Các lỗi khác (400, 404…) fail ngay vì retry vô nghĩa. Timeout mỗi request 30 giây.

`load_raw_records` quan trọng cho pha 2: bước **repair** phục hồi dữ liệu từ raw snapshot chứ không phải từ clean CSV đã hỏng. Đã kiểm tra round-trip `fetch → ghi file → load` cho kết quả trùng khớp tuyệt đối (24/24 record identical).

---

## 5. Artifacts sinh ra

| File | Kích thước | Nội dung |
|---|---|---|
| `data/raw/crossref_response.json` | 239 KB | Response gốc nguyên vẹn, phục vụ truy vết |
| `data/raw/crossref_records.json` | 62 KB | 24 record đã parse theo `PaperRecord` |

### Kết quả lần chạy 2026-08-06

| Chỉ số | Giá trị |
|---|---|
| Tổng kết quả khớp trên Crossref | 100.622 |
| Số item lấy về | 24 |
| Số record parse hợp lệ | **24 / 24** |
| DOI duy nhất | 24 |
| Khoảng ngày xuất bản | 2026-02-12 → 2026-08-01 |
| Độ dài abstract trung bình | 1.724 ký tự (826 – 2.601) |
| Record thiếu tác giả | 0 |
| Record thiếu `pdf_url` | 16 / 24 |
| Còn sót markup/entity | 0 |

Chất lượng đủ tốt để sang bước 4:

- **`summary` dày** (trung bình ~1.7k ký tự) — đủ ngữ liệu cho embedding và cho câu hỏi loại summary.
- **Ngày trải đều 6 tháng** — freshness report và corruption "làm cũ ngày" sẽ có tín hiệu rõ ràng.
- **`pdf_url` rỗng 16/24** là bình thường, trường này không tham gia embedding hay evaluation.

---

## 6. Điểm cần lưu ý cho các bước sau

1. **`categories` hiện là tên tạp chí, không phải chủ đề học thuật.** Field `subject` của Crossref gần như đã bị bỏ hoang nên fallback về `container-title`. Câu hỏi loại `what categories` ở bước 5 vẫn chạy đúng, nhưng ground truth sẽ là tên tạp chí — cần ý thức điều này khi đọc metric.

2. **Corpus đa ngôn ngữ.** Có vài abstract tiếng Nga, Indonesia. Embedding model `all-MiniLM-L6-v2` chủ yếu huấn luyện tiếng Anh nên retrieval trên các record đó sẽ yếu hơn. Nếu muốn corpus thuần Anh, có thể thêm `filter=language:en` — nhưng lưu ý Crossref rất nhiều record bỏ trống field `language`, lọc như vậy sẽ cắt mất phần lớn kết quả.

3. **Chạy lại là refetch.** `fetch_source_records` luôn gọi API và ghi đè `data/raw/`. Vì `from-pub-date` tính theo ngày hiện tại nên kết quả mỗi ngày một khác. `Settings` có sẵn cờ `refresh_source` để pipeline ở bước 9 quyết định fetch mới hay dùng lại snapshot — nên tôn trọng cờ này để kết quả baseline tái lập được.
