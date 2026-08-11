"""
Curator Agent (Tác vụ #13) - điều phối 3 kiểm tra chạy TỰ ĐỘNG lúc
ingest 1 tài liệu mới: quét chỉ dẫn ẩn, kiểm tra chất lượng, phát hiện
gần trùng lặp.

PHẠM VI MVP (đã thảo luận và chốt cùng người dùng): CHỈ 3/6 chức năng
Curator Agent trong đặc tả gốc - injection scan, quality gate, semantic
dedup. KHÔNG làm draft summary (tốn thêm 1 lượt gọi LLM/tài liệu) và
gap analysis (cần syllabus có cấu trúc, dự án chưa có) ở giai đoạn này.

Không có kiểm tra nào ở đây TỰ ĐỘNG TỪ CHỐI tài liệu - tất cả chỉ ghi
cảnh báo vào curator_notes, con người (giảng viên) là người quyết định
cuối cùng lúc duyệt (HITL - Human-In-The-Loop).

Kết quả trả về là app.curator.schemas.CuratorReport (JSON có cấu trúc
cố định) - xem file đó để biết lý do đổi từ 1 chuỗi text tự do sang
schema 3 bước riêng biệt.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.curator.dedup import check_dedup
from app.curator.injection_scan import scan_for_hidden_instructions
from app.curator.quality_gate import check_quality
from app.curator.schemas import CuratorReport


async def run_curator_checks(
    session: AsyncSession,
    *,
    course_id: int,
    full_text: str,
    avg_chars_per_page: float,
    image_count: int,
    total_pages: int,
    document_embedding: list[float],
    exclude_document_id: int | None = None,
) -> CuratorReport:
    injection_result = scan_for_hidden_instructions(full_text)

    quality_result = check_quality(
        avg_chars_per_page=avg_chars_per_page, image_count=image_count, total_pages=total_pages
    )

    dedup_result = await check_dedup(
        session, course_id=course_id, new_embedding=document_embedding, exclude_document_id=exclude_document_id
    )

    return CuratorReport(injection_scan=injection_result, quality_gate=quality_result, dedup=dedup_result)
