"""
Điều phối: ghép 3 bước Parse -> Chunk -> Embed lại với nhau, rồi ghi
kết quả vào Database - biến 1 file PDF thành các dòng thật trong bảng
`document` và `chunk`.

Đây là hàm mà endpoint POST /v1/documents/upload sẽ gọi.
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.curator.curator import run_curator_checks
from app.db.models import Chunk, Document
from app.ingestion.chunker import chunk_document
from app.ingestion.embedder import EMBEDDING_VERSION, embed_texts
from app.ingestion.parser import parse_pdf


# Ngưỡng phát hiện "PDF khả năng là bản scan" (ảnh chụp trang sách,
# không có text layer thật): số ký tự trích được trung bình mỗi trang.
# Một trang giáo trình bình thường có hàng trăm tới hàng nghìn ký tự;
# một trang scan thuần (dù PyMuPDF vẫn có thể bắt được vài ký tự rác
# từ watermark/số trang in kiểu vector) hiếm khi vượt qua vài chục.
# Con số 50 là ước lượng thực dụng, không phải ngưỡng khoa học tuyệt đối.
MIN_AVG_CHARS_PER_PAGE = 50


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
    visibility: str = "COURSE",
) -> Document:
    """
    Chạy trọn vẹn pipeline cho 1 file PDF, trả về Document đã lưu với
    status='PENDING_REVIEW' - CHƯA khả dụng cho Hybrid Search ngay,
    phải đợi giảng viên duyệt (xem app/instructor/router.py, Tác vụ
    #13 - HITL).

    license_status mặc định "OPEN": phù hợp cho tài liệu mở (vd:
    OpenStax, CC BY-NC-SA) - hiện chưa có UI cho giảng viên tự chọn
    license_status khác lúc upload, dùng giá trị mặc định này.
    """
    content_hash = compute_content_hash(file_bytes)

    # Chặn trùng lặp SỚM (trước khi tốn công parse/embed) - kiểm tra
    # ở tầng ứng dụng để trả lỗi rõ ràng, thay vì để tới lúc INSERT
    # mới vỡ ra lỗi UNIQUE constraint khó hiểu với người gọi API.
    existing = await session.execute(select(Document).where(Document.content_hash == content_hash))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Tài liệu này (cùng nội dung) đã được ingest trước đó.")

    # --- Bước 1+2: Parse rồi Chunk ---
    parse_result = parse_pdf(file_path)
    blocks = parse_result.blocks
    if not blocks:
        raise ValueError("Không đọc được nội dung nào từ file - có thể là PDF scan (ảnh), chưa hỗ trợ ở tác vụ này.")

    # Phát hiện PDF SCAN "một phần": khác với trường hợp 0 block ở trên
    # (chặn được ngay), một file scan vẫn có thể lọt qua bước đó nếu
    # PyMuPDF bắt được vài mẩu text vector rải rác (watermark, số trang,
    # chữ ký...). Không chặn dựa trên "có block hay không" mà dựa trên
    # MẬT ĐỘ ký tự trung bình mỗi trang - phản ánh đúng bản chất "trang
    # này có nội dung đọc được hay chỉ là ảnh".
    pages_with_text = {block.page_number for block in blocks}
    total_chars = sum(len(block.text) for block in blocks)
    avg_chars_per_page = total_chars / len(pages_with_text)
    if avg_chars_per_page < MIN_AVG_CHARS_PER_PAGE:
        raise ValueError(
            "File có vẻ là bản scan (ảnh chụp trang sách, không có lớp văn bản thật) "
            "- hệ thống chưa hỗ trợ OCR ở giai đoạn này."
        )

    chunk_drafts = chunk_document(blocks)

    # --- Bước 3: Embed toàn bộ chunk trong 1 loạt batch call ---
    vectors = embed_texts([c.content for c in chunk_drafts])

    # Vector "đại diện" cho cả tài liệu = trung bình cộng vector các
    # chunk - KHÔNG tốn thêm lượt gọi API embedding nào (tái dùng
    # `vectors` vừa tính ở trên), dùng cho Curator Agent phát hiện gần
    # trùng lặp (xem app/curator/dedup.py).
    dimension = len(vectors[0])
    document_embedding = [sum(v[i] for v in vectors) / len(vectors) for i in range(dimension)]

    # --- Bước 4: Ghi vào Database ---
    document = Document(
        course_id=course_id,
        title=title,
        storage_uri=storage_uri,
        content_hash=content_hash,
        license_status=license_status,
        # Tác vụ #13 (HITL): tài liệu KHÔNG còn tự động khả dụng ngay -
        # phải chờ giảng viên duyệt (chuyển sang APPROVED) mới được
        # Hybrid Search tìm thấy (xem app/retrieval/hybrid_search.py).
        status="PENDING_REVIEW",
        uploaded_by=uploaded_by,
        image_count=parse_result.image_count,
        embedding=document_embedding,
    )
    session.add(document)
    await session.flush()  # để document.id có giá trị, dùng gán cho các chunk bên dưới

    # --- Curator Agent: quét chỉ dẫn ẩn + kiểm tra chất lượng + gần
    # trùng lặp - CHỈ ghi cảnh báo, KHÔNG tự động từ chối (con người
    # quyết định lúc duyệt, xem docstring app/curator/curator.py). ---
    full_text = "\n".join(block.text for block in blocks)
    curator_report = await run_curator_checks(
        session,
        course_id=course_id,
        full_text=full_text,
        avg_chars_per_page=avg_chars_per_page,
        image_count=parse_result.image_count,
        total_pages=len(pages_with_text),
        document_embedding=document_embedding,
        exclude_document_id=document.id,
    )
    document.curator_notes = curator_report.model_dump_json()

    # Versioning: nếu cùng course đã có (các) document TRÙNG TIÊU ĐỀ và
    # CHƯA bị thay thế, coi bản mới này là bản kế tiếp - đánh dấu các
    # bản cũ đó "đã thay thế", để Retrieval sau này chỉ tìm trong bản
    # mới nhất (WHERE superseded_by_id IS NULL), tránh trộn lẫn nội
    # dung cũ/mới của cùng 1 tài liệu trong câu trả lời AI.
    #
    # So khớp bằng TIÊU ĐỀ (không phải content_hash - hash chắc chắn
    # khác nhau vì nội dung đã đổi): đây là suy đoán thực dụng dựa trên
    # thói quen đặt tên file giữ nguyên khi upload bản chỉnh sửa, không
    # phải nhận diện ngữ nghĩa "đây có phải cùng 1 tài liệu không".
    previous_versions = await session.execute(
        select(Document).where(
            Document.course_id == course_id,
            Document.title == title,
            Document.superseded_by_id.is_(None),
            Document.id != document.id,
        )
    )
    for old_document in previous_versions.scalars().all():
        old_document.superseded_by_id = document.id

    for draft, vector in zip(chunk_drafts, vectors):
        session.add(
            Chunk(
                document_id=document.id,
                course_id=course_id,
                ord=draft.ord,
                content=draft.content,
                content_type=draft.content_type,
                context_prefix=draft.heading_context,
                page_number=draft.page_number,
                embedding=vector,
                embedding_version=EMBEDDING_VERSION,
                # Áp cho MỌI chunk của tài liệu - quyền truy cập là
                # thuộc tính của cả tài liệu, không phải của từng đoạn.
                # Lưu ở tầng chunk vì đó là nơi Hybrid Search lọc
                # (xem app/retrieval/access_policy.py).
                visibility=visibility,
            )
        )

    await session.commit()
    await session.refresh(document)
    return document
