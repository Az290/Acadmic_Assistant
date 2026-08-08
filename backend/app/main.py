"""
Điểm khởi động của Backend (bộ não xử lý của Academic Assistant).

File này là nơi FastAPI "sống" - mọi request từ frontend (trình duyệt của
người dùng) sẽ đi qua đây trước tiên.

Ở giai đoạn này (Tác vụ #1), file chỉ có 1 endpoint duy nhất: /healthz
Đây là quy ước chuẩn trong ngành để kiểm tra "server có đang sống không?"
- Fly.io (nơi sẽ host backend) sẽ tự động gọi endpoint này định kỳ.
  Nếu không trả lời -> Fly.io biết server bị treo và tự khởi động lại.
"""

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

app = FastAPI(
    title="Academic Assistant API",
    description="Backend cho hệ thống Trợ lý Học thuật đa agent",
    version="0.1.0",
)


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
    Kiểm tra backend có kết nối được tới Database không (Tác vụ #2).

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
