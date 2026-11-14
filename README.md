# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Học viên:** Nguyễn Tuấn Anh (`2A202604089` · Lớp `L3B`)

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| **59 trang nội dung hợp lệ** (từ 73 trang PDF gốc của 4 tài liệu chuẩn IETF RFC) | **3 cấu hình** (A: Fixed-size 500/50, B: Paragraph-aware 650, C: Paragraph-aware 650 + Metadata Filter) | **20 câu hỏi** (15 Dev / 5 Test, gồm 5 câu kiểm tra lọc Metadata) |

---

## Hướng dẫn Setup và Chạy tái lập (Reproducibility Guide)

### 1. Công nghệ và Phiên bản sử dụng
- **Python:** `3.12.10`
- **PDF Parsing & Normalization:** `pypdf==7.1.0` + `unicodedata` (`NFKC`)
- **Embedding Model (Local, \$0.00 cost):** `sentence-transformers/all-MiniLM-L6-v2` (`sentence-transformers==6.3.0`, `384` chiều, chuẩn hóa L2)
- **Vector Store (Local Persistent Storage):** **Qdrant Local** (`qdrant-client==1.20.0`), lưu bền vững trên đĩa tại `starter/qdrant_storage/`, metric `Cosine` (`exact=True`)

### 2. Lệnh cài đặt và chạy toàn bộ Pipeline
Từ thư mục gốc của repository (trên Windows PowerShell):

```powershell
cd starter
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env -ErrorAction SilentlyContinue

# 1. Kiểm tra kết nối Vector Store & cấu hình Embedding Model
.\.venv\Scripts\python.exe scripts/check_setup.py

# 2. Chạy toàn bộ pipeline (Ingestion -> Chunking A/B/C -> Embedding -> Qdrant Upsert -> Re-ingestion Check -> Benchmark Top-3)
.\.venv\Scripts\python.exe -m src.run

# 3. Xuất các bảng kiểm toán thủ công (Coherence, Metadata Usefulness, Grounding Quality)
.\.venv\Scripts\python.exe scripts/generate_manual_audits.py
```

---

## Cấu trúc Bài nộp và Đường dẫn Artifacts

| Thành phần | Đường dẫn trong Repo | Mô tả |
|---|---|---|
| **Thông tin học viên** | [STUDENT.md](STUDENT.md) | Họ tên, MSSV, lớp, chủ đề corpus và link repo |
| **Dữ liệu nguồn (PDF)** | `data/raw/rfc8693.pdf`, `rfc8725.pdf`, `rfc9068.pdf`, `rfc9126.pdf` | 4 tài liệu chuẩn IETF RFC về OAuth 2.0 & JWT Security (73 trang vật lý, 59 trang hợp lệ) |
| **Manifest dữ liệu** | [data/manifest.json](data/manifest.json) | Nguồn URL, giấy phép IETF TLP 5.0, quy tắc tính trang, danh sách trang hợp lệ và trang bị loại |
| **Bộ câu hỏi Benchmark** | [benchmark/questions.json](benchmark/questions.json) | 20 câu hỏi (15 Dev / 5 Test) kèm `evidence_quote` khớp 100% nguyên văn và `filter` |
| **Mã nguồn Pipeline** | `starter/src/` (`ingestion.py`, `chunking.py`, `embeddings.py`, `store.py`, `evaluation.py`, `run.py`) | Toàn bộ mã nguồn xử lý PDF, chia chunk A/B/C, nhúng vector, lưu Qdrant và chấm điểm |
| **Nhật ký thí nghiệm** | [artifacts/experiment_log.csv](artifacts/experiment_log.csv) | Cấu hình, giả thuyết và kết quả Hit@1 / Hit@3 của 3 chiến lược A, B, C |
| **Traces & Thống kê** | [results/metrics_summary.json](results/metrics_summary.json), [results/traces_A.json](results/traces_A.json), [results/traces_B.json](results/traces_B.json), [results/traces_C.json](results/traces_C.json) | Kết quả truy xuất top-3 chi tiết cho từng câu hỏi và kiểm tra nạp lại ([results/reingestion_check.json](results/reingestion_check.json)) |
| **Kiểm toán thủ công** | [results/manual_coherence_audit.csv](results/manual_coherence_audit.csv), [results/manual_metadata_audit.csv](results/manual_metadata_audit.csv), [results/manual_grounding_audit.csv](results/manual_grounding_audit.csv) | Nhãn và lý do chấm thủ công cho Chunk Coherence (30 mẫu), Metadata (45 mẫu) và Grounding (15 mẫu) |
| **Báo cáo cá nhân** | [report/individual/2A202604089_NguyenTuanAnh.md](report/individual/2A202604089_NguyenTuanAnh.md) | Báo cáo phân tích đầy đủ 5 tiêu chí, đánh đổi chiến lược và ví dụ lỗi |

---

## Tài liệu hướng dẫn gốc của Lab

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |
