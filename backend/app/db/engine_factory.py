"""
Tạo async engine đúng cách cho Neon Postgres + driver asyncpg.

Vì sao cần file riêng thay vì viết thẳng trong session.py: cả app lúc
chạy thật (session.py) VÀ Alembic lúc chạy migration (migrations/env.py)
đều cần tạo engine - nếu viết logic xử lý URL ở 2 nơi, dễ bị lệch nhau
khi sửa sau này. Gom về 1 hàm dùng chung.

--- Vấn đề kỹ thuật đang xử lý ---
Neon cung cấp connection string dạng:
    postgresql://user:pass@host/db?sslmode=require
"sslmode=require" là cú pháp cho driver ĐỒNG BỘ (psycopg2) - driver
asyncpg (bất đồng bộ, đang dùng trong dự án) không hiểu tham số này,
gây lỗi "unexpected keyword argument 'ssl'" nếu để nguyên trong URL.

Cách sửa: gỡ "sslmode" ra khỏi URL, rồi tự bật SSL qua `connect_args`
theo đúng cú pháp asyncpg hiểu.
"""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def build_async_engine(database_url: str) -> AsyncEngine:
    """
    Nhận vào DATABASE_URL thô (có thể chứa ?sslmode=require kiểu Neon),
    trả về async engine đã cấu hình SSL đúng cách cho asyncpg.
    """
    parsed = urlparse(database_url)
    query_params = parse_qs(parsed.query)

    # Neon luôn yêu cầu SSL - nếu URL có sslmode=require (hoặc bất kỳ
    # giá trị nào không phải "disable"), ta bật SSL qua connect_args
    # thay vì để asyncpg tự đọc "sslmode" (nó không hiểu tham số này).
    wants_ssl = query_params.pop("sslmode", ["require"])[0] != "disable"

    # Dựng lại URL không còn "sslmode" trong query string
    clean_query = urlencode(query_params, doseq=True)
    clean_url = urlunparse(parsed._replace(query=clean_query))

    connect_args = {"ssl": True} if wants_ssl else {}

    return create_async_engine(clean_url, echo=False, pool_pre_ping=True, connect_args=connect_args)
