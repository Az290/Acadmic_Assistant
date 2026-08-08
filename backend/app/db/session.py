"""
Quản lý kết nối tới Database - "cây cầu" giữa code Python và Postgres.

Dùng async engine (bất đồng bộ) vì FastAPI chạy async: trong lúc chờ
Postgres trả kết quả cho 1 request, server vẫn có thể xử lý request
khác song song - quan trọng khi có nhiều người dùng cùng lúc.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.engine_factory import build_async_engine

settings = get_settings()

# build_async_engine (thay vì gọi create_async_engine trực tiếp) xử lý
# đúng tham số SSL mà Neon yêu cầu - xem chi tiết trong engine_factory.py.
# pool_pre_ping=True (bên trong hàm đó): trước mỗi lần dùng kết nối cũ,
# kiểm tra nó còn sống không - Neon (serverless) có thể tự đóng kết nối
# nhàn rỗi để tiết kiệm tài nguyên, cờ này tránh lỗi "kết nối đã chết".
engine = build_async_engine(settings.database_url)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Cấp một "phiên làm việc" (session) với DB cho mỗi request.

    Đây là một FastAPI "dependency" - mỗi endpoint cần truy vấn DB sẽ
    khai báo dùng hàm này, và FastAPI tự động gọi nó, đưa session vào,
    rồi tự đóng session sau khi request xong (kể cả khi có lỗi).
    """
    async with AsyncSessionLocal() as session:
        yield session
