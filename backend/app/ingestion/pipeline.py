"""
Điều phối: ghép 3 bước Parse -> Chunk -> Embed lại với nhau, rồi ghi
kết quả vào Database - biến 1 file PDF thành các dòng thật trong bảng
`document` và `chunk`.

Đây là hàm mà endpoint POST /v1/documents/upload sẽ gọi.
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document
from app.ingestion.chunker import chunk_document
from app.ingestion.embedder import EMBEDDING_VERSION, embed_texts
from app.ingestion.parser import parse_pdf


def compute_content_hash(file_bytes: bytes) -> str:
    """
    Băm SHA-256 nội dung file - dùng để chống việc ingest trùng lặp
    (đúng 1 file được upload 2 lần sẽ có cùng hash, cột content_hash
    trong bảng document có ràng buộc UNIQUE nên lần 2 sẽ bị chặn ở
    tầng database, không cần tự viết logic kiểm tra trùng thủ công).

    Đây là hash của TOÀN BỘ file gốc, ở cấp document - khác với hash
    (nếu có) của mỗi chunk riêng lẻ.
    """
    return hashlib.sha256(file_bytes).hexdigest()


async def ingest_document(
    session: AsyncSession,
    *,
    file_path: str,
    file_bytes: bytes,
    title: str,
    course_id: int,
    storage_uri: str,
    uploaded_by: int,
    license_status: str = "OPEN",
) -> Document:
    """
    Chạy trọn vẹn pipeline cho 1 file PDF, trả về Document đã lưu.

    license_status mặc định "OPEN": phù hợp cho tài liệu mở (vd:
    OpenStax, CC BY-NC-SA) - khi có luồng duyệt tài liệu (giảng viên
    xác nhận trước khi công khai), giảng viên sẽ tự chọn đúng
    license_status lúc upload thay vì dùng giá trị mặc định này.
    """
    content_hash = compute_content_hash(file_bytes)

    # Chặn trùng lặp SỚM (trước khi tốn công parse/embed) - kiểm tra
    # ở tầng ứng dụng để trả lỗi rõ ràng, thay vì để tới lúc INSERT
    # mới vỡ ra lỗi UNIQUE constraint khó hiểu với người gọi API.
    existing = await session.execute(select(Document).where(Document.content_hash == content_hash))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Tài liệu này (cùng nội dung) đã được ingest trước đó.")

    # --- Bước 1+2: Parse rồi Chunk ---
    blocks = parse_pdf(file_path)
    if not blocks:
        raise ValueError("Không đọc được nội dung nào từ file - có thể là PDF scan (ảnh), chưa hỗ trợ ở tác vụ này.")

    chunk_drafts = chunk_document(blocks)

    # --- Bước 3: Embed toàn bộ chunk trong 1 loạt batch call ---
    vectors = embed_texts([c.content for c in chunk_drafts])

    # --- Bước 4: Ghi vào Database ---
    document = Document(
        course_id=course_id,
        title=title,
        storage_uri=storage_uri,
        content_hash=content_hash,
        license_status=license_status,
        status="DRAFT",  # chuyển sang APPROVED sau khi giáo viên duyệt (luồng duyệt tài liệu)
        uploaded_by=uploaded_by,
    )
    session.add(document)
    await session.flush()  # để document.id có giá trị, dùng gán cho các chunk bên dưới

    for draft, vector in zip(chunk_drafts, vectors):
        session.add(
            Chunk(
                document_id=document.id,
                course_id=course_id,
                ord=draft.ord,
                content=draft.content,
                context_prefix=draft.heading_context,
                page_number=draft.page_number,
                embedding=vector,
                embedding_version=EMBEDDING_VERSION,
            )
        )

    await session.commit()
    await session.refresh(document)
    return document
