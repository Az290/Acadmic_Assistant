# Academic Assistant

Nền tảng trợ lý học thuật dựa trên RAG, phạm vi theo từng lớp học: sinh viên hỏi đáp **có trích dẫn** từ đúng tài liệu giảng viên đã duyệt, luyện quiz bám tài liệu, và theo lộ trình học cá nhân hoá. Giảng viên quản lý lớp bằng **hội thoại tự nhiên** với trợ lý Nova.

**🔗 Demo:** https://acadmic-assistant.vercel.app/

> Tài khoản dùng thử có sẵn ngay tại trang đăng nhập (2 nút "Xem demo Giảng viên" / "Xem demo Sinh viên").

---

## Vấn đề giải quyết

| Vấn đề thực tế | Cách hệ thống xử lý |
|---|---|
| Chatbot AI trả lời "nghe hợp lý" nhưng bịa, không kiểm chứng được | Mọi câu trả lời học thuật bắt buộc bám tài liệu đã duyệt, kèm trích dẫn mở được đúng đoạn nguồn; có bước xác minh trích dẫn sau sinh |
| Tài liệu học rải rác, sinh viên không biết lớp có kiến thức gì để hỏi | Kho tài liệu theo lớp, đọc trực tiếp bản PDF gốc trong lớp |
| Sinh viên gõ tiếng Việt không dấu → tìm kiếm trả về rỗng (~31% lưu lượng đo được) | Phát hiện + khôi phục dấu bằng LLM trước khi truy hồi |
| Giảng viên tốn thời gian ra đề, soạn câu hỏi thủ công | Nova sinh đề bám tài liệu thật, giảng viên duyệt/sửa/góp ý cho AI sửa lại rồi mới giao |
| Rủi ro prompt injection, lộ tài liệu giữa các lớp | Guardrail nhiều lớp + ACL ở tầng truy vấn + kiểm tra lại quyền khi AI thực thi hành động |

---

## Tính năng chính

### Cho sinh viên
- **Hỏi đáp có trích dẫn** — trả lời chỉ dựa trên tài liệu lớp đã duyệt, bấm vào nguồn để xem nguyên văn đoạn được dùng.
- **Chế độ Gia sư (Socratic)** — gợi mở từng bước theo mức độ nắm vững thay vì đưa đáp án ngay.
- **Nova nhớ bài làm sai** — hỏi "giải thích câu vừa rồi" mà không cần nêu rõ câu nào, trợ lý tự biết và giải thích.
- **Quiz + theo dõi mastery**, lộ trình học có khái niệm tiên quyết (khoá/mở theo tiến độ).
- **Đọc tài liệu bản PDF gốc** ngay trong lớp; đóng góp tài liệu để giảng viên duyệt.
- Nhập liệu bằng **giọng nói** (Whisper), tóm tắt hội thoại, câu hỏi gợi ý tiếp theo.

### Cho giảng viên
- **Quản lý lớp qua hội thoại** — Nova thực thi 18 loại hành động (tạo khái niệm, giao bài tập, duyệt/từ chối tài liệu, thêm/gỡ sinh viên, xem thống kê…). Mọi hành động **ghi dữ liệu đều phải xác nhận 2 lượt** trước khi chạy.
- **Sinh đề bám tài liệu** — chọn số câu mỗi khái niệm, AI sinh nháp đa dạng (mỗi câu nhắm một khía cạnh khác nhau), giảng viên **sửa tay / tự soạn thêm / góp ý cho AI sửa lại** rồi mới giao.
- **Duyệt tài liệu (HITL)** — xem bản PDF gốc *và* text đã trích xuất trước khi quyết định; Curator Agent tự quét chỉ dẫn ẩn/trùng lặp/chất lượng.
- **Thống kê lớp** — mastery từng sinh viên, ai cần hỗ trợ, khái niệm hỏi nhiều nhất, **điểm mù tài liệu** (câu hỏi không tìm được nguồn → biết cần bổ sung tài liệu gì), chi phí LLM và độ trễ từng bước pipeline.

---

## Kiến trúc

```
Người dùng
   │
   ▼
Next.js 16 (App Router, React 19, Tailwind 4)   ── SSE streaming ──┐
   │                                                              │
   ▼                                                              │
FastAPI                                                           │
   │                                                              │
   ├─ Guardrail (rule-based → moderation)  ← chặn injection/độc hại│
   ├─ Router Agent  → phân loại 7 nhóm ý định                      │
   ├─ Retrieval: pgvector (cosine) + Postgres FTS → RRF fusion     │
   │     └─ ACL lọc ngay trong SQL (theo lớp + quyền tài liệu)     │
   ├─ Generation (theo prompt riêng từng nhóm ý định) ─────────────┘
   ├─ Citation verifier → loại trích dẫn không khớp nội dung
   └─ Tool executor → thực thi hành động (RBAC kiểm tra lại + audit log)
   │
   ▼
PostgreSQL + pgvector   |   OpenAI (GPT-4o-mini, embeddings, Whisper)
```

**Pipeline hỏi đáp:** Guardrail vào → Phân loại ý định → Lịch sử hội thoại → Truy hồi lai (nếu cần) → Sinh câu trả lời → Guardrail ra → Lưu kèm trích dẫn + đo lường.

**Pipeline nạp tài liệu:** Parse PDF (PyMuPDF) → Chunk theo heading → Embed theo batch → Curator Agent quét → chờ giảng viên duyệt → mới được đưa vào truy hồi.

---

## Điểm kỹ thuật đáng chú ý

**Truy hồi lai + RRF** — kết hợp vector search (ngữ nghĩa) và full-text search (từ khoá chính xác), hợp nhất bằng Reciprocal Rank Fusion. Ngưỡng độ liên quan hiệu chỉnh bằng đo thật, không đoán.

**Tiếng Việt không dấu** — đo được ~31% lưu lượng thật là tiếng Việt không dấu, khiến điểm tương đồng của câu đúng chủ đề *giảm* còn câu lạc đề *tăng* (2 nhóm chồng lấn, không ngưỡng nào tách được). Giải bằng bước khôi phục dấu bằng LLM, chỉ kích hoạt khi heuristic rẻ phát hiện câu nghi ngờ.

**Agentic tool-calling có kiểm soát** — 18 tool, phân theo vai trò. Tool đọc chạy ngay; tool ghi dữ liệu **bắt buộc xác nhận 2 lượt**. Quyền được **kiểm tra lại phía server** (không tin quyền mà LLM ngầm giả định), tham số validate bằng Pydantic, mọi lần thực thi ghi `agent_action_log` để truy vết.

**Chống trùng lặp khi sinh đề** — sinh N câu bằng *một* lời gọi LLM (model thấy được toàn bộ câu nó đang tạo) thay vì gọi lặp N lần độc lập; kèm chỉ dẫn phân hoá khía cạnh/độ khó và mở rộng ngữ cảnh truy hồi.

**Bảo mật nhiều lớp** — chuẩn hoá Unicode + gộp ký tự giãn cách + thử giải mã base64 trước khi khớp mẫu injection; ACL áp ngay trong SQL truy hồi nên không thể lộ tài liệu chéo lớp; tài liệu chưa duyệt không bao giờ vào kết quả tìm kiếm.

**Đo lường vận hành** — token/chi phí và độ trễ từng bước lưu theo từng tin nhắn, phục vụ dashboard chi phí và phát hiện điểm nghẽn bằng số liệu thật.

---

## Công nghệ

**Backend:** Python, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL + pgvector, PyMuPDF, slowapi
**AI:** OpenAI GPT-4o-mini (chat/router/quiz/tool-calling), text-embedding-3-large, Whisper, Moderation API
**Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, SSE
**Hạ tầng:** Vercel (frontend), Neon (Postgres serverless)

---

## Chạy tại máy

**Yêu cầu:** Python 3.11+, Node.js 20+, PostgreSQL 15+ có extension `pgvector`, OpenAI API key.

```bash
# 1. Backend
cd backend
python -m venv .venv && .venv/Scripts/activate     # Windows
# source .venv/bin/activate                        # macOS/Linux
pip install -r requirements.txt

cp .env.example .env        # điền DATABASE_URL, OPENAI_API_KEY, JWT_SECRET
alembic upgrade head        # tạo bảng + seed System Knowledge Base

uvicorn app.main:app --reload --port 8001
```

```bash
# 2. Frontend (terminal khác)
cd frontend
npm install
# tạo .env.local:  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
npm run dev                 # http://localhost:3000
```

```bash
# 3. Kiểm thử hồi quy (server phải đang chạy)
cd backend
REGRESSION_BASE_URL=http://127.0.0.1:8001 python -X utf8 scripts/regression_test.py
```

Bộ kiểm thử gồm **37 case** phủ 9 nhóm: smoke, xác thực/phân quyền, hỏi đáp, guardrail, người dùng chưa vào lớp, đo lường, lộ trình học, streaming SSE và các trường hợp biên. Chạy trước mỗi lần commit.

---

## Cấu trúc thư mục

```
backend/app/
├── academic_agent/    # Agent chính: pipeline hỏi đáp, tool-calling, prompt, tóm tắt
│   ├── agent.py          # Điều phối 7 bước + nhánh thực thi hành động
│   ├── tools.py          # Khai báo 18 tool theo vai trò
│   ├── tool_executor.py  # Thực thi + RBAC kiểm tra lại + ghi audit log
│   └── citation_verifier.py
├── router_agent/      # Phân loại ý định (7 nhóm), chiến lược rule → LLM
├── guardrail/         # Chặn injection/nội dung độc hại (rule + moderation)
├── retrieval/         # Hybrid search, RRF, chính sách ACL dùng chung
├── ingestion/         # Parse PDF → chunk → embed → lưu
├── curator/           # Quét tài liệu trước khi giảng viên duyệt
├── learning/          # Concept, quiz, mastery, assignment, learning path
├── instructor/        # Thống kê lớp, duyệt tài liệu, chi phí, pipeline timing
├── courses/           # Lớp học, ghi danh, danh sách sinh viên
├── documents/         # Upload, liệt kê, đọc nội dung/PDF gốc
└── voice/             # Chuyển giọng nói thành văn bản (Whisper)

frontend/app/(dashboard)/
├── student/  mastery/  quiz/  history/     # Không gian sinh viên
├── courses/[courseId]/                     # Vào lớp: đọc tài liệu PDF gốc
├── assignments/                            # Sinh đề → duyệt → giao / làm bài
├── instructor/  review/                    # Thống kê lớp, duyệt tài liệu
└── documents/                              # Đóng góp/tải tài liệu lên
```

---

## Quyết định thiết kế đáng chú ý

- **Không dùng framework agent** (LangGraph…) — luồng xử lý là rẽ nhánh xác định trước, không phải vòng lặp AI tự quyết định. Function-calling được thêm dưới dạng *một nhánh* trong pipeline sẵn có, giữ nguyên tính dự đoán được.
- **Tài liệu phải qua người duyệt** — sinh viên đóng góp được, nhưng không nội dung nào vào kho tra cứu mà không có giảng viên phê duyệt.
- **Không hiển thị số liệu kỹ thuật cho người học** — độ tương đồng truy hồi được đặt tên là "độ khớp tài liệu" và ẩn sau tooltip, tránh bị hiểu nhầm thành "xác suất trả lời đúng".
- **Chi phí là ràng buộc thiết kế** — dùng model rẻ cho mọi tác vụ, cache câu hỏi quiz, chiến lược "rule rẻ trước, LLM sau" ở guardrail và phân loại ý định.
