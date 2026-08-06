# Bước 7 — Cấu hình LLM provider

File tham khảo: `src/retrieval/llm.py`, `src/core/config.py`, `.env.example`
Bước này **không phải viết code** — nhiệm vụ là đọc hiểu cách ba thứ ăn khớp với nhau: `LLM_PROVIDER`, `LLM_MODEL` và các API key.

---

## 1. Danh sách provider và cách chọn qua `LLM_PROVIDER`

### Sáu provider được hỗ trợ

| `LLM_PROVIDER` | Class LangChain | Package | Cần credential |
|---|---|---|---|
| `gemini` *(mặc định)* | `ChatGoogleGenerativeAI` | `langchain-google-genai` | `GOOGLE_API_KEY` |
| `openai` | `ChatOpenAI` | `langchain-openai` | `OPENAI_API_KEY` |
| `anthropic` | `ChatAnthropic` | `langchain-anthropic` | `ANTHROPIC_API_KEY` |
| `openrouter` | `ChatOpenAI` + `base_url` | `langchain-openai` | `OPENROUTER_API_KEY` |
| `ollama` | `ChatOllama` | `langchain-ollama` | **không cần** |
| `custom` | `ChatOpenAI` + `base_url` | `langchain-openai` | chỉ cần `CUSTOM_LLM_BASE_URL` |

Ba trong sáu provider (`openai`, `openrouter`, `custom`) dùng **chung class `ChatOpenAI`**, chỉ khác nhau ở `base_url` và `api_key`. Đây là toàn bộ ý nghĩa của cụm "OpenAI-compatible": bất kỳ endpoint nào nói được giao thức `/v1/chat/completions` đều cắm vào được mà không cần thêm code.

### Luồng chọn provider

`build_llm` ([llm.py:11-53](../src/retrieval/llm.py#L11-L53)) chạy đúng 3 bước:

```python
provider = normalized_provider(settings)      # 1. chuẩn hóa chuỗi
require_llm_credentials(settings)             # 2. kiểm tra credential, fail sớm
if provider == "gemini": return ChatGoogleGenerativeAI(...)   # 3. dựng client
```

Thứ tự này quan trọng: **credential được kiểm tra trước khi tạo client**. Nếu thiếu key, chương trình báo lỗi rõ ràng ngay tại chỗ (`GOOGLE_API_KEY is required when LLM_PROVIDER=gemini.`) thay vì để lỗi 401 xuất hiện tận lúc gọi API — lúc đó đã chạy được nửa pipeline.

### Chuẩn hóa chuỗi `LLM_PROVIDER`

`normalized_provider` ([config.py:138-144](../src/core/config.py#L138-L144)):

```python
provider = settings.llm_provider.strip().lower().replace(" ", "").replace("-", "")
if provider == "anthorpic":  return "anthropic"    # alias cho lỗi gõ phổ biến
if provider == "customllm":  return "custom"
return provider
```

Nghĩa là các giá trị dưới đây đều hợp lệ:

| Bạn gõ | Sau chuẩn hóa |
|---|---|
| `Gemini`, ` GEMINI `, `gemini` | `gemini` |
| `Open AI`, `open-ai`, `OpenAI` | `openai` |
| `Open Router`, `open-router` | `openrouter` |
| `custom-llm`, `Custom LLM`, `customllm` | `custom` |
| `anthorpic` *(gõ sai)* | `anthropic` |

Hai điều cần biết:

- Alias `anthorpic` là **cố ý** — người viết starter dự đoán trước lỗi gõ hay gặp và bắt lấy nó.
- Chuẩn hóa **chỉ bỏ dấu cách và dấu gạch ngang**, không bỏ gạch dưới. `open_router` sẽ **không** nhận diện được và bị coi là provider lạ.

### Provider không hợp lệ

Chuỗi không khớp provider nào sẽ bị `require_llm_credentials` chặn ([config.py:171-173](../src/core/config.py#L171-L173)):

```
Unsupported LLM_PROVIDER. Expected one of: openai, gemini, anthropic, openrouter, ollama, custom.
```

Dòng `raise` cuối `build_llm` ([llm.py:53](../src/retrieval/llm.py#L53)) trên thực tế **không bao giờ chạy tới**, vì `require_llm_credentials` đã chặn từ trước. Đó là lớp phòng thủ dự phòng phòng khi hai hàm bị sửa lệch nhau về sau.

---

## 2. `LLM_MODEL` map với từng provider như thế nào

### Cơ chế: truyền thẳng, không validate

```python
model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
```

`LLM_MODEL` là **một chuỗi tự do duy nhất**, dùng chung cho mọi provider. Không có bảng ánh xạ, không có danh sách hợp lệ, không có kiểm tra. Giá trị được truyền nguyên vẹn vào tham số `model=` của class LangChain tương ứng.

Hệ quả quan trọng: **`LLM_MODEL` và `LLM_PROVIDER` phải khớp nhau thủ công.** Đây là điểm dễ sai nhất của cấu hình này.

| `LLM_PROVIDER` | `LLM_MODEL` hợp lệ | Sai ở chỗ |
|---|---|---|
| `gemini` | `gemini-2.5-flash` | ✅ khớp |
| `openai` | `gemini-2.5-flash` | ❌ OpenAI không biết model này → lỗi 404 khi gọi API |
| `anthropic` | `gpt-4o` | ❌ tương tự |

Đổi provider mà quên đổi model sẽ **không có lỗi nào lúc khởi động**. Client dựng lên bình thường, pipeline chạy qua ingestion, cleaning, embedding — rồi mới chết ở lần gọi LLM đầu tiên, tức tận bước evaluation.

### Model id mẫu cho từng provider

| Provider | Ví dụ `LLM_MODEL` | Quy ước đặt tên |
|---|---|---|
| `gemini` | `gemini-2.5-flash`, `gemini-2.5-pro` | Tên model của Google |
| `openai` | `gpt-4o-mini`, `gpt-4o` | Tên model của OpenAI |
| `anthropic` | `claude-sonnet-4-5`, `claude-haiku-4-5` | Tên model của Anthropic |
| `openrouter` | `anthropic/claude-sonnet-4.5`, `openai/gpt-4o-mini` | **Bắt buộc có tiền tố `vendor/`** |
| `ollama` | `llama3.1`, `qwen2.5`, `mistral` | Tên tag local, phải `ollama pull` trước |
| `custom` | tùy endpoint | Do server phía sau quy định |

`openrouter` là trường hợp dễ vấp nhất: model id **bắt buộc** có tiền tố nhà cung cấp. `claude-sonnet-4-5` sẽ lỗi, phải viết `anthropic/claude-sonnet-4.5`.

### `temperature` cố định bằng 0

```python
def build_llm(settings: Settings, temperature: float = 0.0):
```

Mặc định `0.0`, và cả ba nơi gọi (`agent`, `judge`, `ragas`) đều dùng giá trị mặc định này. Đây không phải chi tiết vụn: bài lab so sánh metric giữa baseline / corrupted / repaired, nên LLM phải càng tất định càng tốt. Nếu `temperature > 0`, chênh lệch metric có thể đến từ sự ngẫu nhiên của model chứ không phải từ chất lượng dữ liệu — đúng thứ cần loại trừ.

---

## 3. API key được cấu hình và đọc như thế nào

### Toàn bộ biến môi trường

Từ `.env.example` và `load_settings` ([config.py:111-135](../src/core/config.py#L111-L135)):

| Biến môi trường | Provider dùng | Mặc định nếu bỏ trống |
|---|---|---|
| `LLM_PROVIDER` | tất cả | `gemini` |
| `LLM_MODEL` | tất cả | `gemini-2.5-flash` |
| `GOOGLE_API_KEY` | gemini | `None` |
| `OPENAI_API_KEY` | openai | `None` |
| `ANTHROPIC_API_KEY` | anthropic | `None` |
| `OPENROUTER_API_KEY` | openrouter | `None` |
| `OPENROUTER_BASE_URL` | openrouter | `https://openrouter.ai/api/v1` |
| `OLLAMA_BASE_URL` | ollama | `http://localhost:11434` |
| `CUSTOM_LLM_API_KEY` | custom | `None` |
| `CUSTOM_LLM_BASE_URL` | custom | `None` |

Ngoài LLM còn 3 biến khác không liên quan provider: `REFRESH_SOURCE`, `REFRESH_TEST_SET` (nhận `1`/`true`/`yes`), và `RUN_RAGAS` đọc riêng trong `metrics.py`.

### Nạp `.env` từ hai vị trí

```python
load_dotenv(workspace / ".env")              # thư mục CHA của project
load_dotenv(root / ".env", override=False)   # thư mục project
```

[config.py:76-77](../src/core/config.py#L76-L77) — với `workspace = root.parent`. Thứ tự ưu tiên từ cao xuống thấp:

```
biến môi trường thật của shell   >   <thư-mục-cha>/.env   >   <project>/.env
```

Hai điểm dễ gây bất ngờ:

1. **File `.env` ở thư mục cha thắng file `.env` trong project.** Thiết kế này để nhiều project lab trong cùng workspace dùng chung một bộ key. Nhưng nếu bạn sửa `.env` trong project mà không thấy tác dụng, hãy kiểm tra thư mục cha trước tiên.
2. **`export` trong shell thắng cả hai file.** `python-dotenv` mặc định không ghi đè biến đã có sẵn trong `os.environ`.

### Kiểm tra credential theo từng provider

`require_llm_credentials` ([config.py:147-173](../src/core/config.py#L147-L173)) — mỗi provider có luật riêng:

| Provider | Điều kiện bắt buộc | Thông báo lỗi khi thiếu |
|---|---|---|
| `gemini` | có `GOOGLE_API_KEY` | `GOOGLE_API_KEY is required when LLM_PROVIDER=gemini.` |
| `openai` | có `OPENAI_API_KEY` | `OPENAI_API_KEY is required when LLM_PROVIDER=openai.` |
| `anthropic` | có `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic.` |
| `openrouter` | có `OPENROUTER_API_KEY` | `OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter.` |
| `ollama` | **không kiểm tra gì** | — |
| `custom` | có `CUSTOM_LLM_BASE_URL` | `CUSTOM_LLM_BASE_URL is required when LLM_PROVIDER=custom.` |

Hai ngoại lệ đáng chú ý:

- **`ollama` return ngay lập tức** — model chạy local, không có khái niệm API key. Nhưng cũng có nghĩa là **không hề kiểm tra Ollama đã chạy chưa**; nếu daemon chưa bật, lỗi kết nối chỉ xuất hiện lúc gọi thật.
- **`custom` kiểm tra `base_url` chứ không kiểm tra key.** Khi dựng client: `api_key=settings.custom_llm_api_key or "unused"` ([llm.py:49](../src/retrieval/llm.py#L49)). Chuỗi giả `"unused"` tồn tại vì SDK OpenAI bắt buộc phải có `api_key`, trong khi nhiều endpoint tự host (vLLM, LM Studio, LocalAI) không cần xác thực.

### Khác biệt nhỏ về tên tham số

```python
ChatGoogleGenerativeAI(model=..., google_api_key=settings.google_api_key, ...)   # google_api_key
ChatOpenAI(model=..., api_key=settings.openai_api_key, ...)                     # api_key
ChatAnthropic(model=..., api_key=settings.anthropic_api_key, ...)               # api_key
```

Riêng Gemini dùng `google_api_key=` thay vì `api_key=` — do quy ước của package `langchain-google-genai`.

---

## 4. Cấu hình `.env` mẫu cho từng provider

**Gemini** (mặc định của project, có free tier):
```dotenv
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GOOGLE_API_KEY=AIza...
```

**OpenAI:**
```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

**Anthropic:**
```dotenv
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-...
```

**OpenRouter** — lưu ý tiền tố `vendor/`:
```dotenv
LLM_PROVIDER=openrouter
LLM_MODEL=anthropic/claude-sonnet-4.5
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

**Ollama** — chạy local, không cần key, nhớ `ollama pull llama3.1` trước:
```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434
```

**Custom OpenAI-compatible** (vLLM / LM Studio / LocalAI):
```dotenv
LLM_PROVIDER=custom
LLM_MODEL=<tên model của server>
CUSTOM_LLM_BASE_URL=http://localhost:8000/v1
CUSTOM_LLM_API_KEY=
```

---

## 5. `build_llm` được gọi ở đâu

Ba nơi, và mỗi nơi có yêu cầu khác nhau với provider:

| Nơi gọi | Mục đích | Yêu cầu đặc biệt |
|---|---|---|
| [agent.py:40](../src/retrieval/agent.py#L40) | LLM cho agent có tool | Cần **tool calling** |
| [metrics.py:62](../src/evaluation/metrics.py#L62) | LLM judge chấm câu trả lời | Cần **structured output** |
| [metrics.py:95](../src/evaluation/metrics.py#L95) | LLM cho Ragas | Chỉ khi `RUN_RAGAS=1` |

### Yêu cầu structured output

```python
llm = build_llm(settings, temperature=0.0).with_structured_output(JudgeVerdict)
```

`JudgeVerdict` là model Pydantic gồm `score` (1–5), `correct` (bool), `reasoning` (str). `.with_structured_output()` dựa trên khả năng function calling / JSON schema của provider.

Bốn provider cloud đều hỗ trợ tốt. **Ollama với model nhỏ thường không** — model 7B hay trả JSON sai định dạng.

### Cơ chế fallback khi LLM không dùng được

[metrics.py:64-70](../src/evaluation/metrics.py#L64-L70) bọc toàn bộ lời gọi judge trong `try/except Exception`, và khi lỗi thì chuyển sang heuristic dựa trên `token_f1`:

| `token_f1` | score | correct |
|---|---|---|
| `≥ 0.95` | 5 | true |
| `≥ 0.50` | 3 | true |
| `< 0.50` | 1 | false |

Nghĩa là **evaluation vẫn chạy được đến cùng dù chưa có API key nào**. `retrieval_hit_rate` và `mean_token_f1` hoàn toàn không phụ thuộc LLM; chỉ `judge_accuracy` và `mean_judge_score` chuyển sang giá trị heuristic. So sánh baseline / corrupted / repaired vẫn có ý nghĩa.

Ngược lại, **agent thì không có fallback**. `build_agent` gọi `build_llm` trực tiếp nên thiếu key sẽ ném `RuntimeError`. Vì vậy phần demo agent ở bước 9 nên bọc try/except hoặc để tùy chọn.

---

## 6. Kết quả chạy kiểm tra thực tế

Chạy ngày 2026-08-06. Trước đó project chưa có `.env` nào, đã tạo bằng `cp .env.example .env` rồi điền `GOOGLE_API_KEY`.

### Nguồn `.env` được nạp

| Vị trí | Trạng thái |
|---|---|
| `/home/long/project/.env` (thư mục cha) | không có |
| `/home/long/project/K3_Day10_HNUETIT/.env` (project) | **có** |

Không có `.env` ở thư mục cha nên không xảy ra tình huống ghi đè đã nói ở mục 3. Cũng không có biến `GOOGLE_API_KEY` nào export sẵn trong shell — toàn bộ cấu hình đến từ `.env` của project.

### Settings sau khi resolve

```
LLM_PROVIDER (thô)  : 'gemini'
  -> normalized     : 'gemini'
LLM_MODEL           : 'gemini-2.5-flash'
embedding_model     : sentence-transformers/all-MiniLM-L6-v2
top_k               : 4
```

| Credential | Trạng thái |
|---|---|
| `GOOGLE_API_KEY` | **đã đặt** (55 ký tự) |
| `OPENAI_API_KEY` | chưa đặt |
| `ANTHROPIC_API_KEY` | chưa đặt |
| `OPENROUTER_API_KEY` | chưa đặt |
| `CUSTOM_LLM_API_KEY` | chưa đặt |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` (mặc định) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` (mặc định) |
| `CUSTOM_LLM_BASE_URL` | chưa đặt |

Provider đang dùng là `gemini` và đã có key → cấu hình hợp lệ, chạy được.

### Kiểm tra chuẩn hóa chuỗi — 17 biến thể

| Đầu vào | Kết quả | |
|---|---|---|
| `'gemini'`, `'Gemini'`, `'  GEMINI  '` | `gemini` | hợp lệ |
| `'OpenAI'`, `'Open AI'`, `'open-ai'` | `openai` | hợp lệ |
| `'Open Router'`, `'open-router'` | `openrouter` | hợp lệ |
| `'Anthropic'`, `'anthorpic'` | `anthropic` | hợp lệ |
| `'custom-llm'`, `'Custom LLM'`, `'customllm'` | `custom` | hợp lệ |
| `'ollama'` | `ollama` | hợp lệ |
| `'open_router'` | `open_router` | **không hợp lệ** |
| `'gpt4'` | `gpt4` | **không hợp lệ** |
| `''` | `''` | **không hợp lệ** |

Xác nhận đúng như đọc code: alias lỗi gõ `anthorpic` được bắt, còn **gạch dưới thì không** — `open_router` rơi thẳng vào nhánh provider lạ.

### Kiểm tra `require_llm_credentials` cho cả 6 provider

Với `.env` chỉ có mỗi `GOOGLE_API_KEY`:

| Provider | Kết quả |
|---|---|
| `gemini` | **PASS** |
| `ollama` | **PASS** (không cần credential) |
| `openai` | `RuntimeError: OPENAI_API_KEY is required when LLM_PROVIDER=openai.` |
| `anthropic` | `RuntimeError: ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic.` |
| `openrouter` | `RuntimeError: OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter.` |
| `custom` | `RuntimeError: CUSTOM_LLM_BASE_URL is required when LLM_PROVIDER=custom.` |
| `gpt4` *(provider lạ)* | `RuntimeError: Unsupported LLM_PROVIDER. Expected one of: openai, gemini, anthropic, openrouter, ollama, custom.` |

Chạy lại với credential giả điền cho từng provider (`openai_api_key="sk-FAKE"`, `custom_llm_base_url="http://localhost:8000/v1"`, …): **cả 5 provider đều PASS**. Xác nhận `custom` chỉ kiểm tra `base_url` chứ không đòi API key, đúng như đọc code ở mục 3.

### Phần chưa chạy được

`build_llm()` chưa dựng được client thật vì `uv sync` chưa hoàn tất — thiếu `langchain_google_genai` và các package langchain khác:

```
ImportError: No module named 'langchain_google_genai'
```

Toàn bộ logic resolve provider, chuẩn hóa chuỗi và kiểm tra credential đều nằm trong `core/config.py` và chỉ phụ thuộc `python-dotenv`, nên đã verify được đầy đủ. Phần còn lại — dựng client và gọi API thật — sẽ kiểm tra ở bước 8 khi chạy agent.

---

## 7. Điểm cần lưu ý

1. **`Settings` là frozen dataclass, đọc env đúng một lần** lúc `load_settings()`. Sửa `.env` giữa chừng không có tác dụng — phải chạy lại pipeline.

2. **Đổi provider phải đổi cả `LLM_MODEL`.** Không có validate, và lỗi chỉ lộ ra ở lần gọi API đầu tiên, tức tận bước evaluation sau khi đã chạy xong ingestion + embedding.

3. **`.env` thư mục cha thắng `.env` project.** Sửa key không thấy tác dụng thì kiểm tra thư mục cha trước.

4. **Không commit `.env`.** `.gitignore` đã có sẵn dòng `.env`, và checklist nộp bài của `README.md` cũng yêu cầu điều này.

5. **Chưa có key vẫn làm được hầu hết bài lab.** Chỉ mất `judge_accuracy` do LLM chấm và phần demo agent. Nhưng để đạt điểm tối đa Mục 5 của rubric (*"Agent chạy tốt, provider abstraction rõ ràng"*) thì cần ít nhất một provider hoạt động thật.
