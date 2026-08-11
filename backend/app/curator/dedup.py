"""
Phát hiện tài liệu GẦN TRÙNG (near-duplicate) với tài liệu khác đã có
trong cùng lớp - khác content_hash (app/ingestion/pipeline.py, chỉ bắt
trùng TUYỆT ĐỐI từng byte, vd re-upload đúng file gốc).

Tình huống thật cần bắt: 2 file KHÁC NHAU về mặt byte (khác định dạng
export, khác lần OCR, đổi vài chữ...) nhưng NỘI DUNG gần như giống hệt
nhau - content_hash sẽ không phát hiện được, nhưng vector ngữ nghĩa
của 2 tài liệu sẽ rất gần nhau.

KHÔNG tốn thêm lượt gọi API embedding nào: dùng lại trung bình cộng
vector các chunk đã tính lúc ingest tài liệu (xem
app/db/models.py::Document.embedding).
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.curator.schemas import CuratorStepResult

# Ngưỡng cosine similarity coi là "gần trùng" - đặc tả gốc đề xuất 0.93.
# Đây là ngưỡng CAO (rất gần), cố tình tránh báo nhầm 2 tài liệu chỉ
# CÙNG CHỦ ĐỀ (vd 2 chương khác nhau của cùng môn học cũng có thể có
# cosine similarity vừa phải do dùng chung thuật ngữ) - chỉ cảnh báo
# khi thực sự nghi ngờ là bản sao/gần như sao chép.
NEAR_DUPLICATE_THRESHOLD = 0.93


@dataclass
class DuplicateMatch:
    document_id: int
    title: str
    similarity: float


async def find_near_duplicate(
    session: AsyncSession, *, course_id: int, new_embedding: list[float], exclude_document_id: int | None = None
) -> DuplicateMatch | None:
    """
    Tìm tài liệu gần trùng nhất trong CÙNG lớp - chỉ so với tài liệu
    CÒN HIỆU LỰC (superseded_by_id IS NULL, không so với bản cũ đã bị
    versioning thay thế - đó là tình huống KHÁC, đã xử lý riêng bằng
    so khớp tiêu đề trong ingestion/pipeline.py).

    exclude_document_id: bỏ qua chính tài liệu vừa tạo (nếu đã insert
    trước khi gọi hàm này).

    Dùng exec_driver_sql() với tham số VỊ TRÍ ($1, $2...) thay vì
    session.execute(text(...)) với tham số TÊN - PHÁT HIỆN QUA LỖI
    THẬT (đã gặp khi test): SQLAlchemy hiểu nhầm cú pháp
    ":new_embedding::vector" (tham số đặt tên đứng ngay trước dấu ép
    kiểu 2 dấu hai chấm của Postgres) - CÙNG VẤN ĐỀ và CÙNG CÁCH SỬA đã
    áp dụng ở app/retrieval/hybrid_search.py::_vector_search().
    """
    conn = await session.connection()
    result = await conn.exec_driver_sql(
        """
        SELECT id, title, 1 - (embedding <=> $1::vector) AS similarity
        FROM document
        WHERE course_id = $2
          AND embedding IS NOT NULL
          AND superseded_by_id IS NULL
          AND id != $3
        ORDER BY embedding <=> $1::vector
        LIMIT 1
        """,
        (str(new_embedding), course_id, exclude_document_id or -1),
    )
    row = result.first()
    if row is None or row.similarity < NEAR_DUPLICATE_THRESHOLD:
        return None

    return DuplicateMatch(document_id=row.id, title=row.title, similarity=row.similarity)


async def check_dedup(
    session: AsyncSession, *, course_id: int, new_embedding: list[float], exclude_document_id: int | None = None
) -> CuratorStepResult:
    """Bọc find_near_duplicate() thành CuratorStepResult cho Curator Agent - xem app/curator/schemas.py."""
    duplicate = await find_near_duplicate(
        session, course_id=course_id, new_embedding=new_embedding, exclude_document_id=exclude_document_id
    )
    if duplicate is None:
        return CuratorStepResult(status="pass", detail="Không tìm thấy tài liệu nào gần trùng trong cùng lớp.")
    return CuratorStepResult(
        status="warn",
        detail=(
            f"Nội dung giống {duplicate.similarity:.0%} với tài liệu đã có "
            f"'{duplicate.title}' (#{duplicate.document_id}) - kiểm tra có phải trùng lặp không."
        ),
    )
