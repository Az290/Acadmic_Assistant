# Academic Assistant

Hệ thống trợ lý học thuật đa agent (hỏi đáp có trích dẫn, gia sư Socratic, kho tài liệu)
dành cho sinh viên/học viên các khóa học. Xây dựng theo hướng **production-lean**:
chi phí hạ tầng tối thiểu, chất lượng đủ dùng thật cho người dùng thật.

## Cấu trúc dự án

```
Acadmic_Assistant/
├── backend/
│   ├── app/
│   │   ├── main.py          # Điểm khởi động server, lắp ráp các router
│   │   ├── config.py         # Đọc cấu hình bí mật từ .env (DB url, API key, JWT...)
│   │   ├── db/
│   │   │   ├── models.py      # Định nghĩa 7 bảng database (SQLAlchemy)
│   │   │   └── session.py     # Quản lý kết nối tới Postgres
│   │   ├── auth/               # Đăng nhập/đăng ký/JWT/phân quyền
│   │   │   ├── security.py      # Băm mật khẩu, tạo/kiểm tra JWT
│   │   │   ├── dependencies.py  # get_current_user, require_role(...)
│   │   │   ├── schemas.py       # Định dạng dữ liệu ra/vào API auth
│   │   │   └── router.py        # 5 endpoint /v1/auth/*
│   │   └── courses/            # "Kênh lớp" của giáo viên
│   │       ├── schemas.py
│   │       └── router.py        # 3 endpoint /v1/courses/*
│   ├── migrations/            # Lịch sử thay đổi cấu trúc database (Alembic)
│   ├── .env.example           # Mẫu file cấu hình — copy thành .env rồi điền giá trị thật
│   └── requirements.txt
├── docs/
│   └── learning-log.html   # 📘 Nhật ký học tập — mở file này để học lý thuyết + quiz
└── README.md            # File bạn đang đọc
```

## Trạng thái hiện tại

- [x] **Tác vụ #1**: Khung xương dự án (backend skeleton, cấu trúc thư mục, learning log)
- [x] **Tác vụ #2**: Database schema (6 bảng, pgvector, Alembic migration)
- [x] **Tác vụ #3**: Auth + Enrollment (đăng nhập/đăng ký/JWT, phân quyền theo role, kênh lớp)
- [ ] Tác vụ #4: Ingestion pipeline (crawl + xử lý tài liệu)
- [ ] ... (cập nhật dần — xem lộ trình đầy đủ trong `docs/learning-log.html`)

## API hiện có (Tác vụ #3)

| Endpoint | Ai gọi được | Việc gì |
|---|---|---|
| `POST /v1/auth/register` | Ai cũng được | Đăng ký email + mật khẩu, role mặc định STUDENT |
| `POST /v1/auth/login` | Ai cũng được | Đăng nhập → JWT trong HttpOnly Cookie |
| `POST /v1/auth/logout` | Đã đăng nhập | Xoá cookie |
| `GET /v1/auth/me` | Đã đăng nhập | Thông tin + role — frontend dùng để điều hướng giao diện |
| `POST /v1/auth/admin/reset-password` | ADMIN/INSTRUCTOR | Reset mật khẩu giúp học sinh (giải pháp "quên mật khẩu" không cần email) |
| `POST /v1/courses` | INSTRUCTOR/ADMIN | Tạo lớp/kênh mới |
| `POST /v1/courses/{id}/enroll` | Giáo viên sở hữu lớp đó | Thêm học sinh (theo email) vào lớp |
| `GET /v1/courses/me` | Đã đăng nhập | Danh sách lớp mình thuộc về |

## Chạy thử backend ở máy local

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate      # Windows
pip install -r requirements.txt

# Copy file cấu hình mẫu rồi điền giá trị thật (DATABASE_URL, OPENAI_API_KEY...)
cp .env.example .env

uvicorn app.main:app --reload
```

Sau đó mở trình duyệt tại `http://127.0.0.1:8000/docs` để xem giao diện API tương tác
(tự động sinh bởi FastAPI).

**Lưu ý:** endpoint `/healthz/db` cần một Postgres thật đang chạy (đã điền đúng
`DATABASE_URL` trong `.env`) mới hoạt động — việc tạo Neon Postgres thật sẽ làm ở
tác vụ deploy riêng.

## Áp dụng migration (khi đã có Postgres thật)

```bash
cd backend
alembic upgrade head
```

Lệnh này tạo toàn bộ 6 bảng + bật pgvector extension + tạo index HNSW trên
Postgres đang trỏ tới trong `.env`.

## Học kiến trúc & lý thuyết

Mở file [`docs/learning-log.html`](docs/learning-log.html) bằng trình duyệt bất kỳ —
đây là nhật ký học tập được cập nhật sau mỗi tác vụ, giải thích lý thuyết, sơ đồ,
code, và có quiz tự kiểm tra kiến thức.
