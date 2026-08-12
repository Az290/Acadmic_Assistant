"""
Chuyển toàn bộ dữ liệu từ 1 database Postgres sang database khác.

DÙNG KHI NÀO: đổi vị trí đặt database (vd chuyển Neon từ Mỹ về
Singapore để giảm độ trễ mạng). KHÔNG dùng cho việc sao lưu định kỳ -
đây là script chạy 1 lần, có chủ đích.

VÌ SAO KHÔNG DÙNG pg_dump: máy dev không cài sẵn PostgreSQL client
tools, và dữ liệu dự án nhỏ (vài nghìn dòng) nên đọc-ghi qua
SQLAlchemy đủ nhanh, không phải cài thêm gì.

AN TOÀN:
- Database NGUỒN chỉ được ĐỌC, không bao giờ ghi/xoá - nếu có sự cố,
  dữ liệu gốc còn nguyên, chỉ cần trỏ lại connection string cũ.
- Database ĐÍCH phải đã chạy `alembic upgrade head` trước (script này
  chỉ copy dữ liệu, không tạo bảng).
- Chạy xong TỰ ĐỘNG đối chiếu số dòng từng bảng, báo lỗi nếu lệch.

Chạy:
    python scripts/migrate_database.py <SOURCE_URL> <TARGET_URL>
"""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

# THỨ TỰ COPY QUAN TRỌNG: bảng được tham chiếu phải copy TRƯỚC bảng
# tham chiếu tới nó, nếu không sẽ vi phạm khoá ngoại. Danh sách này
# xếp theo đúng thứ tự phụ thuộc (cha trước, con sau).
TABLES_IN_ORDER = [
    "app_user",
    "course",
    "enrollment",
    "refresh_token",
    "document",
    "chunk",
    "concept",
    "conversation",
    "message",
    "message_feedback",
    "security_log",
    "student_mastery",
    "quiz_question",
    "quiz_attempt",
    "assignment",
    "assignment_question",
    "assignment_submission",
    "eval_run",
    "eval_case_result",
]

# Cột SINH TỰ ĐỘNG từ cột khác (GENERATED ALWAYS) - Postgres tự tính,
# KHÔNG cho phép INSERT giá trị vào. Phải loại khỏi câu INSERT nếu không
# sẽ lỗi "cannot insert into generated column".
GENERATED_COLUMNS = {"chunk": ["content_tsv"]}


async def get_columns(conn, table: str) -> list[str]:
    result = await conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = :t AND table_schema = 'public'
            ORDER BY ordinal_position
            """
        ),
        {"t": table},
    )
    cols = [row[0] for row in result]
    return [c for c in cols if c not in GENERATED_COLUMNS.get(table, [])]


async def copy_table(source_conn, target_conn, table: str) -> tuple[int, int]:
    """Trả về (số dòng đọc được từ nguồn, số dòng ghi được vào đích)."""
    columns = await get_columns(source_conn, table)
    if not columns:
        print(f"  {table:24} BỎ QUA (không tìm thấy bảng ở nguồn)")
        return 0, 0

    col_list = ", ".join(f'"{c}"' for c in columns)
    rows = (await source_conn.execute(text(f"SELECT {col_list} FROM {table}"))).mappings().all()

    if not rows:
        print(f"  {table:24} 0 dòng (rỗng)")
        return 0, 0

    placeholders = ", ".join(f":{c}" for c in columns)
    insert_sql = text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})")

    # Ghi theo lô để không giữ 1 transaction quá lớn, đồng thời tránh
    # gửi hàng nghìn câu lệnh riêng lẻ qua mạng.
    BATCH = 200
    written = 0
    for i in range(0, len(rows), BATCH):
        batch = [dict(r) for r in rows[i : i + BATCH]]
        await target_conn.execute(insert_sql, batch)
        written += len(batch)

    print(f"  {table:24} {written} dòng")
    return len(rows), written


async def reset_sequences(target_conn) -> None:
    """
    Đặt lại bộ đếm ID tự tăng cho khớp dữ liệu vừa copy.

    BẮT BUỘC PHẢI LÀM: dữ liệu copy sang mang theo id cũ (vd id lớn nhất
    = 300), nhưng bộ đếm ở database mới vẫn đang ở 1 - dòng thêm mới đầu
    tiên sẽ nhận id=1 và đụng độ khoá chính với dòng đã có. Lỗi này chỉ
    xuất hiện lúc người dùng thật thêm dữ liệu, rất dễ bỏ sót khi test.
    """
    result = await target_conn.execute(
        text(
            """
            SELECT c.relname AS seq_name, t.relname AS table_name, a.attname AS column_name
            FROM pg_class c
            JOIN pg_depend d ON d.objid = c.oid
            JOIN pg_class t ON d.refobjid = t.oid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
            WHERE c.relkind = 'S'
            """
        )
    )
    for seq_name, table_name, column_name in result.all():
        await target_conn.execute(
            text(
                f"""
                SELECT setval('{seq_name}',
                    COALESCE((SELECT MAX("{column_name}") FROM {table_name}), 0) + 1,
                    false)
                """
            )
        )
    print("  Đã đặt lại bộ đếm ID tự tăng cho mọi bảng.")


async def main() -> None:
    if len(sys.argv) != 3:
        print("Dùng: python scripts/migrate_database.py <SOURCE_URL> <TARGET_URL>")
        sys.exit(1)

    source_url, target_url = sys.argv[1], sys.argv[2]
    source_engine = create_async_engine(source_url, connect_args={"ssl": "require"})
    target_engine = create_async_engine(target_url, connect_args={"ssl": "require"})

    print("=== COPY DỮ LIỆU ===")
    counts: dict[str, tuple[int, int]] = {}
    async with source_engine.connect() as source_conn:
        async with target_engine.begin() as target_conn:
            for table in TABLES_IN_ORDER:
                counts[table] = await copy_table(source_conn, target_conn, table)
            await reset_sequences(target_conn)

    print("\n=== ĐỐI CHIẾU (đọc lại từ CẢ HAI database) ===")
    all_ok = True
    async with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table in TABLES_IN_ORDER:
            src = (await source_conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar()
            tgt = (await target_conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar()
            status = "OK" if src == tgt else "LỆCH!"
            if src != tgt:
                all_ok = False
            if src or tgt:
                print(f"  {table:24} nguồn={src:<6} đích={tgt:<6} {status}")

    await source_engine.dispose()
    await target_engine.dispose()

    print()
    if all_ok:
        print("HOÀN TẤT: mọi bảng khớp số dòng.")
    else:
        print("CẢNH BÁO: có bảng lệch số dòng - KHÔNG đổi DATABASE_URL cho tới khi xử lý xong.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
