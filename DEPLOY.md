# Hướng dẫn triển khai (đưa hệ thống lên Internet)

Tài liệu này dành cho người **không chuyên kỹ thuật**: làm theo đúng thứ tự,
mỗi bước có giải thích *tại sao cần làm*.

Hệ thống gồm 3 phần chạy ở 3 nơi khác nhau:

| Phần | Chạy ở đâu | Vai trò |
|---|---|---|
| Cơ sở dữ liệu | **Neon** | Lưu tài khoản, tài liệu, lịch sử chat |
| Backend (bộ não) | **Fly.io** | Xử lý câu hỏi, gọi AI, kiểm duyệt |
| Frontend (giao diện) | **Vercel** | Trang web người dùng nhìn thấy |

---

## Bước 0 — Chuẩn bị (làm 1 lần)

Cần có sẵn:

- Tài khoản **Neon** (database) — bạn đã có, đang dùng để chạy thử ở máy
- Tài khoản **Fly.io** — đăng ký tại `fly.io`, **cần gắn thẻ thanh toán**
- Tài khoản **Vercel** — đăng ký tại `vercel.com`, miễn phí cho dự án cá nhân
- Mã nguồn đã đẩy lên **GitHub** (Vercel cần đọc từ đây)

Cài công cụ dòng lệnh của Fly.io (chạy trong PowerShell):

```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

Sau khi cài xong, đăng nhập:

```powershell
fly auth login
```

---

## Bước 1 — Chuẩn bị cơ sở dữ liệu (Neon)

Database hiện tại đang dùng để chạy thử. Bạn có 2 lựa chọn:

- **Dùng luôn database đang có** — nhanh, nhưng dữ liệu test lẫn với dữ liệu thật
- **Tạo database mới cho production** — sạch sẽ, nên làm nếu sắp có người dùng thật

Nếu tạo mới, nhớ bật extension `vector` (bắt buộc cho tìm kiếm ngữ nghĩa):

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Lấy chuỗi kết nối từ Neon, rồi **sửa 2 chỗ**:

1. Đổi `postgresql://` thành `postgresql+asyncpg://`
2. Xoá phần `?sslmode=require` ở cuối

---

## Bước 2 — Triển khai backend (Fly.io)

Mở PowerShell tại thư mục `backend`:

```powershell
cd backend
```

**2.1. Tạo ứng dụng** (chưa chạy ngay, chỉ đăng ký tên):

```powershell
fly launch --no-deploy
```

Khi được hỏi:
- Tên ứng dụng: chọn tên bạn muốn (sẽ thành `<tên>.fly.dev`)
- Khu vực: chọn **Singapore (sin)** — gần Việt Nam nhất
- Tạo database/Redis: **chọn Không** (ta đã có Neon rồi)

**2.2. Tạo ổ đĩa lưu file tài liệu** (nếu không có, file PDF tải lên sẽ mất
mỗi khi máy chủ khởi động lại):

```powershell
fly volumes create uploaded_files --size 1 --region sin
```

**2.3. Đặt các thông tin bí mật.** Đây là bước quan trọng nhất — những giá trị
này **không nằm trong mã nguồn** (nếu nằm trong đó thì ai xem GitHub cũng thấy):

```powershell
fly secrets set DATABASE_URL="postgresql+asyncpg://..." OPENAI_API_KEY="sk-..." JWT_SECRET="<chuỗi ngẫu nhiên>"
```

Sinh chuỗi ngẫu nhiên cho `JWT_SECRET` bằng lệnh:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

**2.4. Đưa lên**:

```powershell
fly deploy
```

Lệnh này tự động: đóng gói ứng dụng → **chạy cập nhật cấu trúc database** →
khởi động máy chủ. Nếu bước cập nhật database lỗi, Fly.io sẽ **huỷ** và giữ
nguyên phiên bản cũ (an toàn cho người dùng đang dùng).

**2.5. Kiểm tra**: mở `https://<tên-app>.fly.dev/healthz` — phải thấy
`{"status":"ok",...}`.

---

## Bước 3 — Triển khai giao diện (Vercel)

1. Vào `vercel.com` → **Add New Project** → chọn kho GitHub của dự án
2. Ở mục **Root Directory**, chọn thư mục `frontend`
3. Ở mục **Environment Variables**, thêm:

   | Tên | Giá trị |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | `https://<tên-app>.fly.dev` |

4. Bấm **Deploy**

Vercel sẽ cho bạn một địa chỉ dạng `https://<tên-dự-án>.vercel.app`.

---

## Bước 4 — Nối 2 bên lại với nhau (BẮT BUỘC)

Backend cần biết địa chỉ frontend, nếu không trình duyệt sẽ chặn mọi yêu cầu.
Chạy trong thư mục `backend`:

```powershell
fly secrets set CORS_ALLOWED_ORIGINS="https://<tên-dự-án>.vercel.app"
```

Máy chủ sẽ tự khởi động lại sau lệnh này.

> **Vì sao bước này bắt buộc:** trình duyệt có quy tắc bảo vệ — chỉ cho phép
> trang web gọi sang máy chủ khác nếu máy chủ đó *nói rõ là cho phép*. Không
> khai báo địa chỉ frontend ở đây thì mọi thao tác đăng nhập, hỏi bài đều
> thất bại dù cả 2 phía đều chạy tốt.

---

## Bước 5 — Kiểm tra toàn bộ

Mở địa chỉ Vercel và thử lần lượt:

- [ ] Đăng ký tài khoản mới
- [ ] Đăng nhập — vào đúng trang theo vai trò
- [ ] Bấm bong bóng chat, hỏi một câu về tài liệu đã có
- [ ] Đăng xuất, đăng nhập lại

Nếu **đăng nhập xong lại bị đá về trang đăng nhập**: gần như chắc chắn do
cookie. Kiểm tra `COOKIE_SAMESITE` đang là `none` (đã đặt sẵn trong
`fly.toml`) và địa chỉ frontend đã khai đúng ở Bước 4.

---

## Chi phí ước tính hằng tháng

| Khoản | Ước tính |
|---|---|
| Fly.io (1 máy 512MB chạy liên tục) | ~$4 |
| Fly.io (ổ đĩa 1GB) | ~$0.15 |
| Neon (gói miễn phí) | $0 |
| Vercel (gói cá nhân) | $0 |
| OpenAI | Theo lượng dùng thật (đo được ~$0.0005/câu hỏi) |

Tổng cố định khoảng **$4–5/tháng**, cộng tiền OpenAI theo mức sử dụng.

> Có thể giảm xuống gần $0 bằng cách cho máy chủ **tự tắt khi rảnh**
> (`auto_stop_machines = true` trong `fly.toml`), đổi lại người dùng đầu tiên
> sau thời gian vắng phải chờ máy khởi động. Dự án đang ưu tiên tốc độ nên
> chọn để máy chạy liên tục.

---

## Những điều đã biết trước, chưa xử lý

Ghi ra để bạn nắm rõ, không phải lỗi bất ngờ:

1. **Người dùng đầu tiên sau thời gian vắng vẫn có thể chờ lâu** — do database
   Neon gói miễn phí tự "ngủ" khi không ai dùng. Khắc phục bằng cách nâng gói
   Neon hoặc đặt lịch gọi định kỳ để giữ nó thức.

2. **Chỉ chạy được 1 máy chủ** — file tài liệu lưu trên ổ đĩa gắn với đúng
   một máy. Muốn chạy nhiều máy song song (khi đông người dùng) thì phải
   chuyển sang lưu trữ đám mây (Cloudflare R2/S3).

3. **Giới hạn chống spam tính riêng từng máy chủ** — hiện đếm trong bộ nhớ
   của tiến trình. Với 1 máy thì đúng; nhiều máy sẽ cần Redis dùng chung.

4. **Chưa có sao lưu tự động** — Neon có sẵn khả năng khôi phục theo thời
   điểm ở gói trả phí; gói miễn phí giới hạn hơn.
