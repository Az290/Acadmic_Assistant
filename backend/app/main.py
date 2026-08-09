"""
Điểm khởi động của Backend (bộ não xử lý của Academic Assistant).

File này là nơi FastAPI "sống" - mọi request từ frontend (trình duyệt của
người dùng) sẽ đi qua đây trước tiên. Các nhóm endpoint theo chủ đề (auth,
courses...) được viết ở file riêng rồi "gắn" (include_router) vào đây -
giữ file này gọn, chỉ đóng vai trò lắp ráp.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import router as auth_router
from app.config import get_settings
from app.courses.router import router as courses_router
from app.db.session import get_db
from app.documents.router import router as documents_router
from app.guardrail.router import router as guardrail_router
from app.logging_config import configure_logging
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.request_id_middleware import RequestIdMiddleware
from app.retrieval.router import router as retrieval_router

configure_logging()

app = FastAPI(
    title="Academic Assistant API",
    description="Backend cho hệ thống Trợ lý Học thuật đa agent",
    version="0.1.0",
)

# Request ID PHẢI được gắn TRƯỚC (ngoài cùng) mọi middleware khác -
# Starlette chạy middleware theo thứ tự khai báo NGƯỢC (middleware
# thêm sau cùng chạy TRƯỚC TIÊN) - đặt add_middleware này trước
# CORSMiddleware bên dưới nghĩa là request_id có sẵn sớm nhất có thể,
# để cả những lỗi xảy ra ở tầng CORS cũng được log kèm đúng id.
app.add_middleware(RequestIdMiddleware)

# Rate limiting: gắn limiter vào app + đăng ký handler xử lý khi vượt
# giới hạn (tự động trả lỗi 429 "Too Many Requests" đúng chuẩn HTTP
# thay vì để lỗi rơi tự do).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: chỉ các domain trong danh sách whitelist (config.cors_allowed_origins)
# mới được trình duyệt cho phép gọi API này bằng JavaScript. Đây là
# điều BẮT BUỘC phải có trước khi frontend (chạy ở domain khác - vd
# Vercel) gọi vào backend (vd Fly.io) - không có middleware này, trình
# duyệt sẽ tự chặn mọi request cross-origin, kể cả khi cả 2 phía code
# đều đúng.
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allowed_origins_list,
    allow_credentials=True,  # BẮT BUỘC để cookie (JWT) được gửi kèm qua cross-origin request
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(documents_router)
app.include_router(retrieval_router)
app.include_router(guardrail_router)


@app.get("/healthz")
def health_check():
    """
    Endpoint kiểm tra "sức khỏe" server.

    Trả về gì: một JSON đơn giản báo server đang chạy tốt.
    Ai gọi nó: hệ thống hạ tầng (Fly.io), không phải người dùng cuối.
    """
    return {"status": "ok", "service": "academic-assistant-api"}


@app.get("/healthz/db")
async def health_check_db(session: AsyncSession = Depends(get_db)):
    """
    Kiểm tra backend có kết nối được tới Database không.

    Khác với /healthz (chỉ kiểm tra server sống), endpoint này thực sự
    gửi 1 câu lệnh nhỏ nhất có thể ("SELECT 1") tới Postgres và chờ
    phản hồi - nếu DATABASE_URL sai hoặc Neon chưa bật, endpoint này
    sẽ báo lỗi rõ ràng thay vì để lỗi xuất hiện âm thầm ở tính năng
    khác về sau.
    """
    result = await session.execute(text("SELECT 1"))
    return {"status": "ok", "db_check": result.scalar()}


@app.get("/")
def root():
    """Trang gốc - chỉ để xác nhận server chạy khi bạn mở link trên trình duyệt."""
    return {
        "message": "Academic Assistant API đang chạy.",
        "docs": "/docs",  # FastAPI tự sinh trang tài liệu API tương tác tại đây
    }
