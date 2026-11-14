# Báo cáo cá nhân — Day 6 · Data Ingestion Engineering

- **Họ và tên:** Nguyễn Tuấn Anh
- **MSSV:** `2A202604089`
- **Lớp:** `L3B`
- **Repo bài nộp:** `https://github.com/TuanAnhNg131/K5-L3B-DAY06-Nguyen-Tuan-Anh-2A202604089-DataIngestionEngineering`

---

## 1. Dữ liệu và pipeline

### 1.1. Chủ đề, nguồn/quyền, số trang và quy tắc tính trang
- **Chủ đề:** Bộ đặc tả kỹ thuật và bảo mật xác thực **IETF OAuth 2.0 & JSON Web Token (JWT) Security Specifications**.
- **Nguồn và giấy phép (`license_or_permission`):** Toàn bộ 4 tài liệu PDF được tải trực tiếp từ kho lưu trữ chính thức của IETF RFC Editor (`https://www.rfc-editor.org/rfc/`), phát hành theo giấy phép **IETF Trust Legal Provisions (TLP 5.0 / BCP 78)** — cho phép sao chép, trích xuất văn bản và phân phối lại nguyên bản phục vụ nghiên cứu, học tập và kỹ thuật. Chi tiết lưu tại [data/manifest.json](../../data/manifest.json).
- **Thống kê số trang vật lý và số trang nội dung hợp lệ:**
  - Tổng số trang vật lý: **73 trang** trên 4 file PDF.
  - Tổng số trang nội dung hợp lệ: **59 trang** (vượt ngưỡng tối thiểu 30 trang nội dung hợp lệ của bài lab), tổng cộng **135.305 ký tự** sau chuẩn hóa.
  - **Quy tắc tính trang hợp lệ:** Chỉ tính các trang PDF vật lý có chứa nội dung đặc tả kỹ thuật thực chất sau khi loại bỏ tiêu đề đầu trang (running header) và chân trang (running footer). Loại bỏ hoàn toàn:
    1. Trang chỉ chứa mục lục (`table_of_contents` — trang 2 của cả 4 RFC); đồng thời cắt bỏ phần mục lục tràn sang đầu trang 3 trước mục `1. Introduction`.
    2. Trang chỉ chứa danh mục tài liệu tham khảo (`references_only`).
    3. Trang chỉ chứa lời cảm ơn và địa chỉ tác giả ở cuối tài liệu (`acknowledgements_or_authors_only`).

| `source_id` | Tiêu đề tài liệu | Năm (`year`) | Phân loại (`category`) | Trang vật lý | Trang hợp lệ | Các trang bị loại (Lý do) | Số ký tự chuẩn hóa |
|---|---|---:|---|---:|---:|---|---:|
| `rfc8693` | RFC 8693: OAuth 2.0 Token Exchange | 2020 | `Standards Track` | 27 | **24** | p.2 (`toc`), p.21 (`refs`), p.27 (`authors`) | 52.345 |
| `rfc8725` | RFC 8725: JSON Web Token Best Current Practices | 2020 | `Best Current Practice` | 13 | **9** | p.2 (`toc`), p.11–12 (`refs`), p.13 (`authors`) | 21.373 |
| `rfc9068` | RFC 9068: JWT Profile for OAuth 2.0 Access Tokens | 2021 | `Standards Track` | 15 | **11** | p.2 (`toc`), p.13–14 (`refs`), p.15 (`authors`) | 26.088 |
| `rfc9126` | RFC 9126: OAuth 2.0 Pushed Authorization Requests (PAR) | 2021 | `Standards Track` | 18 | **15** | p.2 (`toc`), p.17–18 (`refs`) | 35.499 |
| **Tổng** | **4 tài liệu chuẩn IETF RFC** | **2020–2021** | **2 phân loại** | **73** | **59** | **14 trang bị loại** | **135.305** |

### 1.2. Chuẩn hóa, lỗi phát hiện và giới hạn xử lý PDF
- **Đọc và tái tạo thứ tự dòng theo tọa độ (`starter/src/ingestion.py`):**
  - Khi kiểm tra bằng `pypdf` (`pypdf==7.1.0`), các file PDF định dạng XMLv3 của IETF (`rfc8725.pdf`, `rfc9068.pdf`, `rfc9126.pdf`) có đặc điểm kỹ thuật quan trọng: trình kết xuất PDF của RFC Editor xuất các từ khóa chuẩn hóa in đậm (`MUST`, `MUST NOT`, `SHOULD`, `RECOMMENDED`) và các liên kết tham chiếu (`[RFC6749]`, `[RFC7519]`) thành các đối tượng văn bản (`BT ... ET`) nằm cuối luồng trang hoặc lệch thứ tự luồng văn bản thường. Ngoài ra, `rfc8693.pdf` (tháng 1/2020) sử dụng hệ tọa độ PDF gốc từ dưới lên (`cm[3] = +1.0`), trong khi 3 RFC còn lại sử dụng ma trận lật trục dọc từ trên xuống (`cm[3] = -1.0`).
  - **Giải pháp kỹ thuật:** Sử dụng `pdf_page.extract_text(visitor_text=...)` để thu thập tọa độ thực của từng mảnh văn bản, quy đổi thống nhất về khoảng cách từ đỉnh trang `y_top = tm[5] if cm[3] < 0 else (page_height - tm[5])`, lọc bỏ running header (`y_top < 58pt`) và running footer (`y_top > 720pt`), gom các mảnh cùng dòng (`round(y_top, 1)`), và tự động chèn ngắt đoạn `\n\n` khi khoảng cách dọc giữa hai dòng liên tiếp `dy > 17.5pt`.
- **Chuẩn hóa Unicode (`normalize_text`):**
  - Chuẩn hóa Unicode theo dạng **`NFKC`** để biến đổi toàn bộ ký tự ghép (ligatures) phổ biến trong PDF như `ﬁ` (`\ufb01`), `ﬂ` (`\ufb02`), `ﬃ` (`\ufb03`) thành chuỗi ASCII chuẩn (`fi`, `fl`, `ffi` — ví dụ `speciﬁcation` $\rightarrow$ `specification`, `proﬁle` $\rightarrow$ `profile`), chuyển non-breaking space `\xa0` thành khoảng trắng thường, xóa ký tự ẩn (`\u200b`, `\ufeff`, `\xad`) và chuẩn hóa khoảng trắng ngang mà vẫn bảo toàn cấu trúc đoạn `\n\n`.
- **Log kiểm toán quá trình đọc:** Lưu đầy đủ danh sách 14 trang bị loại kèm lý do và độ dài ký tự tại [results/ingestion_log.json](../../results/ingestion_log.json).
- **Giới hạn còn tồn tại:** Trên một số dòng có từ khóa in đậm (`MUST`, `SHOULD`) hoặc trích dẫn `[RFC...]`, dù đã được gom về đúng dòng `y_top`, từ in đậm vẫn nằm ở cuối dòng đó (ví dụ: `JWT access tokens use MUST NOT "none" as the signing algorithm`). Hiện tượng này được giữ nguyên nhất quán giữa corpus và `evidence_quote` để đảm bảo tính xác thực tuyệt đối từ PDF gốc.

### 1.3. Embedding model, Vector store, lệnh chạy và chi phí
- **Embedding Model:**
  - **Provider & Tên model:** Local SentenceTransformers — `sentence-transformers/all-MiniLM-L6-v2` (`sentence-transformers==6.3.0`, `transformers==5.23.0`, `torch==2.15.0`).
  - **Số chiều:** `384` chiều, chuẩn hóa vector đơn vị (`normalize_embeddings=True`).
  - **Cách xử lý query và document:** Dùng chung không gian biểu diễn dense 384 chiều (bi-encoder đối xứng) cho cả `embed_documents` (batch size 32) và `embed_query`; giữ cố định model và tham số giữa cả 3 cấu hình A, B, C. Không sử dụng mock hay vector ngẫu nhiên.
- **Vector Store:**
  - **Hệ lưu trữ & Phiên bản:** **Qdrant Local Persistent Storage** (`qdrant-client==1.20.0`), khởi tạo qua `QdrantClient(path="starter/qdrant_storage")`, lưu bền vững trên đĩa tại `starter/qdrant_storage/` (collection `day06_rag_chunks`).
  - **Metric & Chế độ tìm kiếm:** `Cosine` similarity (`models.Distance.COSINE`), tìm kiếm chính xác (`exact=True`).
  - **Xử lý nạp lại (Idempotency) & Tài liệu thay đổi:** Mỗi chunk được cấp định danh tất định `UUID5(NAMESPACE_DNS, f"{strategy}::{chunk_id}")`. Trước khi `upsert` một tài liệu `document_id`, `store.py` truy vấn các điểm hiện có của `(strategy, document_id)` và xóa mọi chunk cũ không còn nằm trong tập `chunk_id` mới. Kết quả kiểm증 thực tế lưu tại [results/reingestion_check.json](../../results/reingestion_check.json): nạp lại toàn bộ cấu hình B giữ nguyên đúng `286` vector (`duplicates_created = 0`, `idempotent_verified = true`), và thử nghiệm thu gọn tài liệu tự động xóa các chunk dư thừa (`286` $\rightarrow$ `188` $\rightarrow$ khôi phục `286`).
- **Chi phí:** **`$0.00`** (chạy hoàn toàn bằng model local và vector store local trên CPU).
- **Lệnh chạy tái lập:**
  ```powershell
  cd starter
  .\.venv\Scripts\python.exe scripts/check_setup.py
  .\.venv\Scripts\python.exe -m src.run
  .\.venv\Scripts\python.exe scripts/generate_manual_audits.py
  ```

### 1.4. Metadata bắt buộc và trường lọc bổ sung
- **Metadata bắt buộc (truy vết nguồn):**
  - `document_id` (`str`): Mã định danh tài liệu (`"rfc8693"`, `"rfc8725"`, `"rfc9068"`, `"rfc9126"`).
  - `source` (`str`): Đường dẫn file PDF trong repo (`"data/raw/rfc8693.pdf"`, ...).
  - `page` (`int`): Số trang vật lý trong file PDF (bắt đầu từ 1).
- **Trường lọc và ngữ cảnh bổ sung:**
  - `year` (`int` — giá trị `2020` hoặc `2021`): Năm xuất bản chính thức ghi trên tiêu đề trang 1 của từng RFC (`2020` cho RFC 8693, RFC 8725; `2021` cho RFC 9068, RFC 9126).
  - `category` (`str` — giá trị `"Standards Track"` hoặc `"Best Current Practice"`): Phân loại hiệu lực chuẩn IETF ghi trên phần đầu trang 1 (`"Best Current Practice"` cho RFC 8725; `"Standards Track"` cho 3 RFC còn lại).
  - `section` (`str`): Tiêu đề mục lớn/mục con (ví dụ `"2.1. Header"`, `"3.10. Do Not Trust Received Claims"`) trích xuất trực tiếp từ dòng heading trên trang hoặc đoạn văn bản.
- **Lý do chọn:** Trong bộ tài liệu bảo mật OAuth/JWT, nhiều khái niệm trùng lặp giữa các năm và loại văn bản (ví dụ: quy định về thuật toán `"none"` và header `"typ"` xuất hiện ở cả bản *Best Current Practice* năm 2020 lẫn bản *Standards Track* năm 2021; hay mã trạng thái HTTP `200` vs `201` trong mục *Successful Response* của chuẩn năm 2020 vs 2021). Lọc theo `year` và `category` giúp khoanh vùng đúng phạm vi chuẩn mà **không làm lộ `document_id` hay đáp án**.

---

## 2. Cấu hình và benchmark

### 2.1. Ba cấu hình thử nghiệm (A / B / C)
Ba cấu hình được thiết kế đảm bảo **so sánh có kiểm soát** (thay đổi từng biến số độc lập trên cùng corpus, cùng model embedding và cùng bộ câu hỏi):

| Cấu hình | Phương pháp chia chunk (`chunking.py`) | Kích thước & Overlap | Metadata lưu kèm | Lọc Metadata khi truy xuất (`store.py`) | Mục đích so sánh có kiểm soát |
|---|---|---|---|---|---|
| **A** | `fixed_size`: Cắt cửa sổ ký tự cố định trên từng trang | `size = 500` ký tự, `overlap = 50` ký tự | `document_id`, `source`, `page`, `year`, `category`, `section` | **Không lọc** (`filters=None`) | Baseline chia chunk cố định không xét cấu trúc đoạn/mục |
| **B** | `by_paragraph`: Gom các đoạn văn (`\n\n`) dưới heading mục con; tách theo ranh giới câu nếu đoạn dài quá ngưỡng | `max_size = 650` ký tự, `overlap = 0` | Giống hệt cấu hình A | **Không lọc** (`filters=None`) | **So sánh A vs B:** Chỉ thay đổi chiến lược chunking (cố định vs theo cấu trúc đoạn/heading) |
| **C** | `by_paragraph`: Giống hệt cấu hình B (cùng tập 286 chunks và vectors) | `max_size = 650` ký tự, `overlap = 0` | Giống hệt cấu hình A & B | **Có lọc** theo `year` và `category` khi câu hỏi cung cấp `filter` | **So sánh B vs C:** Chỉ thay đổi duy nhất yếu tố lọc metadata khi truy xuất |

### 2.2. Thiết kế bộ câu hỏi Benchmark (20 câu: 15 Dev / 5 Test)
- Toàn bộ **20 câu hỏi** ([benchmark/questions.json](../../benchmark/questions.json)) được thiết kế và cố định phân tách **trước khi chạy thực nghiệm**:
  - **Tập Dev (15 câu: `q01`–`q15`):** Gồm 5 câu từ `rfc8693`, 4 câu từ `rfc8725`, 3 câu từ `rfc9068`, 3 câu từ `rfc9126`. Phân bố theo loại câu: 5 câu trực tiếp (`direct`), 3 câu diễn đạt lại (`paraphrase`), 4 câu có điều kiện/ngoại lệ (`conditional`), và **3 câu kiểm tra lọc metadata (`metadata_filter`: `q05`, `q09`, `q15`)**.
  - **Tập Test (5 câu: `q16`–`q20`):** Đại diện cả 4 tài liệu (`rfc8693`, `rfc8725`, `rfc9068`, `rfc9126`) và cả 4 loại câu hỏi: 1 câu `paraphrase` (`q16`), 1 câu `direct` (`q19`), 1 câu `conditional` (`q20`), và **2 câu `metadata_filter` (`q17`, `q18`)**.
- **Kiểm chứng bằng chứng (`evidence_quote`):** Tất cả 20/20 đoạn `evidence_quote` đã được kiểm tra tự động bằng script xác nhận nằm nguyên văn 100% trong văn bản trang nguồn (`gold_source_id`, `gold_page`) sau chuẩn hóa. Các câu có `filter` chỉ sử dụng thông tin ngữ cảnh (`year`, `category`) được cung cấp trước khi truy xuất; các câu không có `filter` chạy không lọc ở cả 3 cấu hình.

### 2.3. Tiêu chí chọn chiến lược chốt trước khi xem tập Test
Trước khi đọc kết quả trên tập Test, tiêu chí lựa chọn chiến lược trên tập Dev được chốt theo thứ tự ưu tiên:
1. **Ưu tiên 1:** Điểm **Evidence Hit@3** trên tập Dev cao nhất (và số lỗi cắt đứt bằng chứng `SplitErr` thấp nhất).
2. **Ưu tiên 2:** Điểm **Hit@1** trên tập Dev, tỷ lệ tuân thủ filter và điểm đánh giá thủ công **Chunk Coherence** cao hơn.
3. **Ưu tiên 3:** Chi phí lưu trữ (số lượng chunk) và thời gian nạp dữ liệu thấp hơn.

---

## 3. Kết quả

### 3.1. Bảng kết quả độ chính xác truy xuất và tài nguyên (Tiêu chí 1 & 5)

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Lỗi tách bằng chứng (`SplitErr`) | Chunk count | Tổng ký tự (Tokens xấp xỉ) | Thời gian Ingest | Chi phí |
|---|---|---|---|---:|---:|---:|---:|---:|
| **A** (`fixed_size=500, overlap=50`) | **dev** | `4/15` (26.7%) | `7/15` (46.7%) | 6 | 323 | 148.440 (~37.123) | 20.99s | \$0.00 |
| **A** (`fixed_size=500, overlap=50`) | **test** | `0/5` (0.0%) | `0/5` (0.0%) | 3 | 323 | 148.440 (~37.123) | 20.99s | \$0.00 |
| **B** (`by_paragraph=650, no filter`) | **dev** | `9/15` (60.0%) | `13/15` (86.7%) | 0 | 286 | 134.903 (~33.728) | 19.16s | \$0.00 |
| **B** (`by_paragraph=650, no filter`) | **test** | `0/5` (0.0%) | `2/5` (40.0%) | 1 | 286 | 134.903 (~33.728) | 19.16s | \$0.00 |
| **C** (`by_paragraph=650 + filter`) | **dev** | **`10/15` (66.7%)** | **`13/15` (86.7%)** | **0** | **286** | **134.903 (~33.728)** | **18.24s** | **\$0.00** |
| **C** (`by_paragraph=650 + filter`) | **test** | `0/5` (0.0%) | **`2/5` (40.0%)** | 1 | **286** | **134.903 (~33.728)** | **18.24s** | **\$0.00** |

### 3.2. Bảng kết quả kiểm toán thủ công: Coherence, Metadata & Grounding (Tiêu chí 2, 3 & 4)

| Strategy | Coherence trung bình /2 (n=10) | Phân bố Coherence (0 / 1 / 2) | Metadata đủ và đúng trên Test Top-3 (n/N) | Filter tuân thủ Dev (n/N) | Filter tuân thủ Test (n/N) | Grounding 0/1/2 (số câu trên 5 câu Test) và trung bình /2 |
|---|---|---|---|---|---|---|
| **A** | **`1.00 / 2`** (n=10) | `0`: 0, `1`: 10, `2`: 0 | `15/15` (100%) | `1/3` (33.3%) | `1/2` (50.0%) | Mức `0`: 2 câu, Mức `1`: 3 câu, Mức `2`: 0 câu — **TB: `0.60 / 2`** |
| **B** | **`1.80 / 2`** (n=10) | `0`: 0, `1`: 2, `2`: 8 | `15/15` (100%) | `1/3` (33.3%) | `1/2` (50.0%) | Mức `0`: 2 câu, Mức `1`: 0 câu, Mức `2`: 3 câu — **TB: `1.20 / 2`** |
| **C** | **`1.80 / 2`** (n=10) | `0`: 0, `1`: 2, `2`: 8 | `15/15` (100%) | **`3/3` (100%)** | **`2/2` (100%)** | Mức `0`: 2 câu, Mức `1`: 0 câu, Mức `2`: 3 câu — **TB: `1.20 / 2`** |

### 3.3. Đường dẫn trace, nhãn thủ công và cách chọn mẫu
- **Traces truy xuất đầy đủ (top-3 mỗi câu hỏi):**
  - Cấu hình A: [results/traces_A.json](../../results/traces_A.json)
  - Cấu hình B: [results/traces_B.json](../../results/traces_B.json)
  - Cấu hình C: [results/traces_C.json](../../results/traces_C.json)
  - Tổng hợp số liệu tự động: [results/metrics_summary.json](../../results/metrics_summary.json)
- **Mẫu và nhãn chấm thủ công:**
  1. **Chunk Coherence ([results/manual_coherence_audit.csv](../../results/manual_coherence_audit.csv), dữ liệu gốc tại [results/coherence_samples.json](../../results/coherence_samples.json)):** Trước khi xem điểm truy xuất, chọn cố định **10 vị trí nguồn (`coh_01`–`coh_10`)** tại điểm giữa (`len(page.text) // 2`) của 10 trang nội dung trải đều trên 4 tài liệu (`rfc8693` p.4, 5, 7; `rfc8725` p.5, 7, 9; `rfc9068` p.4, 5; `rfc9126` p.6, 8).
     - **Cấu hình A (`1.00/2`):** Cả 10/10 mẫu đều bị điểm `1/2` do cửa sổ cứng 500 ký tự cắt ngang giữa từ ở đầu và cuối chunk (ví dụ `coh_04` tại `rfc8725:p05:fixed:02` cắt đứt câu giải thích lỗ hổng ECDH-ES ngay tại cụm `"resulting from de"`, làm mất hệ quả quan trọng là kẻ tấn công khôi phục được khóa bí mật).
     - **Cấu hình B & C (`1.80/2`):** Đạt điểm `2/2` trên 8/10 mẫu nhờ gom trọn vẹn các đoạn văn và gắn kèm tiêu đề mục con (như `2.5. Insecure Use of Elliptic Curve Encryption` ở `coh_04` hay `3.10. Do Not Trust Received Claims` ở `coh_06`). Có 2 mẫu đạt `1/2` (`coh_05` có câu dẫn cuối đoạn mở đầu cho danh sách gạch đầu dòng ở chunk sau; `coh_08` bắt đầu bằng đại từ `"Their values are fixed..."` mà tiền ngữ `auth_time, acr, amr` nằm ở câu cuối của chunk liền trước).
  2. **Metadata Usefulness ([results/manual_metadata_audit.csv](../../results/manual_metadata_audit.csv)):** Kiểm tra thủ công toàn bộ `5 câu test × top-3 = 15 bản ghi` cho mỗi chiến lược (tổng 45 bản ghi). Cả `15/15` bản ghi ở mỗi chiến lược đều gắn đúng và đủ `document_id`, `source`, `page`, `year`, `category`, `section` khớp với PDF gốc. Tuy nhiên:
     - **Điểm hữu dụng:** Trường `year` và `category` giúp cấu hình C loại bỏ hoàn toàn các chunk nhiễu khác chuẩn/năm (đạt tuân thủ filter `3/3` trên Dev và `2/2` trên Test, so với `1/3` trên Dev và `1/2` trên Test của A và B). Trường `section` ở cấu hình B/C giữ được tiêu đề mục con chính xác (như `"2.1. Header"`), hỗ trợ người đọc đối chiếu nguồn nhanh hơn hẳn tiêu đề mục cấp trang của cấu hình A.
     - **Hạn chế của metadata:** Lọc theo `year` và `category` chỉ thu hẹp phạm vi đến cấp độ tài liệu/phân loại chuẩn chứ không phân biệt được các mục con bên trong cùng một RFC (ví dụ ở câu `q17`, dù lọc đúng vào `rfc8725`, truy xuất vẫn lấy trang 4 và 6 thay vì trang 9).
  3. **Grounding Quality ([results/manual_grounding_audit.csv](../../results/manual_grounding_audit.csv)):** Chấm thủ công 5 câu test (`q16`–`q20`) trên từng cấu hình:
     - **Cấu hình A (`0.60/2`):** Có 3 câu đạt mức `1/2` (`q16`, `q18`, `q20`) vì dù tìm được đúng trang nguồn trong top-3 nhưng cửa sổ 500 ký tự làm mất vế điều kiện hoặc cắt cụt tên tham số (`q20` bị cắt ngay sau `"regardless of other authorization server metadata such as"`, làm mất hai tham số cần trả lời là `request_uri_parameter_supported` và `require_request_uri_registration`); 2 câu đạt mức `0/2` (`q17`, `q19`).
     - **Cấu hình B & C (`1.20/2`):** Có **3/5 câu đạt mức `2/2`** (`q16`, `q18`, `q20`) và 2 câu mức `0/2` (`q17`, `q19`). Đáng chú ý ở câu **`q18`**, mặc dù chỉ số tự động `Evidence Hit@3` đơn chunk báo `False` vì đoạn bằng chứng dài gồm 2 đoạn văn nằm ở hai chunk liên tiếp (`rfc9068:p04:para:02` ở Rank 2 và `rfc9068:p04:para:03` ở Rank 1), khi chấm Grounding trên toàn bộ **top-3**, cả 2 đoạn văn đều có mặt đầy đủ trong top-3 nên cung cấp trọn vẹn 100% bằng chứng và điều kiện để trả lời câu hỏi (đạt mức `2/2`).

---

## 4. Phân tích và kết luận (Tiêu chí 5: Data Strategy Impact)

### 4.1. So sánh có kiểm soát A–B (Chunking) và B–C (Metadata Filtering) kèm ví dụ lỗi cụ thể
1. **Tác động của chiến lược Chunking (A vs B):**
   - Chuyển từ chia cố định 500 ký tự (`A`) sang chia theo cấu trúc đoạn/heading tối đa 650 ký tự (`B`) giúp **giảm 11,5% số lượng chunk** (`323` $\rightarrow$ `286` chunks), giảm thời gian nạp (`20.99s` $\rightarrow$ `19.16s`), nhưng **tăng mạnh Dev Hit@1 từ `4/15` (26.7%) lên `9/15` (60.0%)** và **Dev Evidence Hit@3 từ `7/15` (46.7%) lên `13/15` (86.7%)**, đồng thời nâng điểm Coherence trung bình từ `1.00/2` lên `1.80/2`.
   - **Ví dụ lỗi 1 — Cắt đứt bằng chứng do cửa sổ cố định (`q20`, nguồn `rfc9126` trang 14):** Câu hỏi yêu cầu tìm giá trị mặc định của `require_pushed_authorization_requests` và điều kiện sử dụng `request_uri` độc lập với `request_uri_parameter_supported`. Ở **Strategy A**, chunk Rank 1 (`rfc9126:p14:fixed:00`, score `0.8463`) dừng đúng ở ký tự thứ 500: *"...usable at the authorization endpoint regardless of other authorization server metadata such as"*, cắt mất tên hai tham số ở dòng tiếp theo (`SplitErr = True`, Hit@3 = False, Grounding = 1/2). Ở **Strategy B & C**, chunk `rfc9126:p14:para:00` (Rank 2, score `0.8319`, dài 535 ký tự) giữ trọn cả hai đoạn văn, trả về đầy đủ bằng chứng (Hit@3 = True, Grounding = 2/2).
2. **Tác động của lọc Metadata (B vs C):**
   - Giữ nguyên cách chia chunk của B và chỉ bật bộ lọc `year` + `category` khi câu hỏi có ngữ cảnh lọc (`C`) không làm tăng chi phí lưu trữ (`286` chunks) nhưng giúp **tăng Dev Hit@1 từ `9/15` (60.0%) lên `10/15` (66.7%)** và nâng **tỷ lệ tuân thủ filter từ `1/3` (Dev) và `1/2` (Test) lên tuyệt đối `3/3` (Dev) và `2/2` (Test) — 100%**.
   - **Ví dụ lỗi 2 — Nhiễu chéo giữa các đặc tả khi không lọc metadata (`q05`, nguồn `rfc8693` trang 9):** Câu hỏi hỏi về mã trạng thái HTTP và media type của phản hồi thành công theo chuẩn *2020 Standards Track*. Khi không lọc (**Strategy B**), cả `rfc9126` (năm 2021) và `rfc8693` (năm 2020) đều có mục tên là `Successful Response`. Do câu hỏi nhắc tới cụm *"HTTP status code"*, vector query khớp mạnh hơn với câu *"provide it in the MUST response with a 201 HTTP status code"* của `rfc9126:p08:para:02` (Rank 1, score `0.7414`, năm 2021 — sai tài liệu!) hơn là chunk đúng `rfc8693:p09:para:00` (Rank 2, score `0.7050`, năm 2020, HTTP 200). Khi bật lọc `{"year": 2020, "category": "Standards Track"}` ở **Strategy C**, các chunk năm 2021 của `rfc9126` bị loại bỏ ngay tại tầng Qdrant index, đưa `rfc8693:p09:para:00` lên thẳng **Rank 1** (`Hit@1 = True`).
3. **Ví dụ lỗi 3 — Thất bại của Dense Embedding với ký hiệu kỹ thuật ngắn (`q17`, nguồn `rfc8725` trang 9):**
   - Câu hỏi `q17` (Test) hỏi về lỗ hổng SSRF khi đi theo URL trong header `"jku"` hoặc `"x5u"` của JWT và cách phòng chống. Cả 3 chiến lược A, B, C đều trượt (`Hit@3 = False`, Grounding = `0/2`): ngay cả khi Strategy C đã lọc đúng vào tài liệu `rfc8725` (`year=2020, category="Best Current Practice"`), mô hình dense `all-MiniLM-L6-v2` vẫn xếp các đoạn nói chung về tấn công JWT ở trang 6 (`rfc8725:p06:para:01` — *Cross-JWT Confusion*, score `0.6969`) và trang 4 (`rfc8725:p04:para:01`, score `0.6683`) cao hơn mục `3.10. Do Not Trust Received Claims` ở trang 9 (nơi xuất hiện chính xác hai từ khóa hiếm `"jku"` và `"x5u"`). Đây là minh chứng điển hình cho giới hạn của pure dense retrieval đối với các định danh kỹ thuật ngắn.

### 4.2. Chiến lược được chọn, đánh đổi và điều kiện áp dụng
- **Chiến lược được chọn:** **Strategy C (`by_paragraph` với `max_size=650` kết hợp lọc metadata `year`, `category`)** được chọn dựa trên các tiêu chí đã chốt trên tập Dev (đạt `Dev Evidence Hit@3 = 13/15 (86.7%)`, `Dev Hit@1 = 10/15 (66.7%)`, `Coherence = 1.80/2`, `Filter Compliance = 100%`, và chỉ tốn `286` chunks).
- **Các đánh đổi (Trade-offs):**
  - *Chunking theo đoạn (`B/C`) vs Cố định (`A`):* Đòi hỏi bước tiền xử lý PDF phức tạp hơn (phải khôi phục khoảng cách dòng `y_top` để tách đoạn `\n\n` và nhận diện dòng heading) và độ dài chunk biến thiên nhiều hơn (`30` đến `650` ký tự so với `500` ký tự đồng nhất của A). Đổi lại, nó loại bỏ hoàn toàn 6 lỗi cắt ngang bằng chứng trên tập Dev và giảm 11,5% số vector cần lưu.
  - *Có lọc Metadata (`C`) vs Không lọc (`B`):* Đảm bảo độ chính xác phạm vi 100% và cải thiện Hit@1 khi người dùng/ngữ cảnh cung cấp metadata đúng; nhưng có rủi ro **false negative** nếu metadata đầu vào của truy vấn bị gán sai (ví dụ người dùng nhớ nhầm RFC 9068 xuất bản năm 2020 thay vì 2021 thì bộ lọc cứng sẽ loại mất đáp án đúng).
- **Điều kiện áp dụng:** Phù hợp cho các kho tài liệu kỹ thuật, quy chế, chính sách có cấu trúc mục/đoạn rõ ràng và có các thuộc tính phân loại đáng tin cậy (năm ban hành, phiên bản, loại văn bản). Không suy rộng kết quả này ra ngoài phạm vi corpus đặc tả kỹ thuật IETF đang xét.

### 4.3. Hạn chế của dữ liệu, nhãn, tập test nhỏ và công cụ hỗ trợ
- **Hạn chế của tập Test nhỏ (`N = 5`):** Trên tập Test 5 câu, mỗi câu tương ứng tới 20% điểm số. Việc có 2 câu khó về từ khóa kỹ thuật hiếm (`q17` với `jku`/`x5u` và `q19` với quy tắc dùng 1 lần của `request_uri`) cùng 1 câu có bằng chứng trải qua 2 đoạn văn (`q18`) khiến chỉ số tự động `Evidence Hit@3` đơn chunk trên Test chỉ đạt `2/5 (40.0%)` dù Grounding thực tế trên top-3 của B và C đạt `3/5` câu ở mức tối đa `2/2`. Tập test nhỏ chỉ mang tính minh họa kiểm tra quy trình holdout, không dùng để kết luận tổng quát.
- **Thiên lệch người chấm (Annotator Bias):** Người thực hiện chấm thủ công Coherence, Metadata và Grounding chính là tác giả xây dựng pipeline. Để giảm thiểu thiên lệch, 10 vị trí chấm Coherence đã được cố định tự động theo công thức điểm giữa trang trước khi xem kết quả, và toàn bộ nhận xét từng mẫu đều được công bố minh bạch trong các file CSV tại `results/`.
- **Ghi nhận sử dụng công cụ AI (`RULES.md`):** Quá trình thực hiện có sử dụng AI assistant (Antigravity) để hỗ trợ viết mã nguồn khung pipeline Python (`starter/src/`), kiểm tra lỗi `grpcio` trên Windows Smart App Control và định dạng bảng biểu báo cáo; toàn bộ văn bản trích xuất, nhãn `evidence_quote`, kết quả chạy thực nghiệm và điểm audit đều được kiểm chứng trực tiếp từ dữ liệu chạy thật của chương trình.

### 4.4. Hướng cải tiến nếu làm lại hoặc mở rộng
1. **Kết hợp Hybrid Retrieval (Dense + BM25 / Lexical):** Như đã thấy ở lỗi câu `q17` (`"jku"`, `"x5u"`) và `q19` (`"only use a request_uri value once"`), kết hợp điểm tương đồng ngữ nghĩa của `all-MiniLM-L6-v2` với điểm khớp từ khóa chính xác BM25 (Reciprocal Rank Fusion) sẽ giải quyết triệt để các truy vấn chứa tên trường và hằng số kỹ thuật hiếm.
2. **Sliding Paragraph Window / Parent-Child Retrieval:** Ở câu `q18`, hai đoạn văn liên tiếp trong cùng mục `2.1. Header` có tổng độ dài `1.103` ký tự (`> max_size=650`) nên bị tách thành 2 chunk (`para:02` và `para:03`). Áp dụng kỹ thuật *Small-to-Big (Parent-Child)* — nhúng vector trên từng đoạn văn nhỏ nhưng trả về toàn bộ mục con (`Section 2.1`) hoặc ghép overlap 1 đoạn văn liền kề — sẽ giúp cả chỉ số đơn chunk lẫn Grounding đều đạt tối đa.
