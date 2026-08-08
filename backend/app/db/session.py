"""
Quản lý kết nối tới Database - "cây cầu" giữa code Python và Postgres.

Dùng async engine (bất đồng bộ) vì FastAPI chạy async: trong lúc chờ
Postgres trả kết quả cho 1 request, server vẫn có thể xử lý request
khác song song - quan trọng khi có nhiều người dùng cùng lúc (đúng bài
toán "hàng nghìn request" đã bàn trước đó).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

# pool_pre_ping=True: trước mỗi lần dùng kết nối cũ, kiểm tra nó còn sống
# không. Neon (serverless) có thể tự đóng kết nối nhàn rỗi để tiết kiệm
# tài nguyên - cờ này tránh lỗi "kết nối đã chết" khó hiểu.

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
