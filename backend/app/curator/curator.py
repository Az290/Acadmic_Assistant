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
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.curator.dedup import find_near_duplicate
from app.curator.injection_scan import scan_for_hidden_instructions
from app.curator.quality_gate import check_quality


@dataclass
class CuratorReport:
    notes: str | None  # None nếu không có cảnh báo nào - Document.curator_notes để trống, không phải chuỗi rỗng


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
    warnings: list[str] = []

    injection_warning = scan_for_hidden_instructions(full_text)
    if injection_warning:
        warnings.append(injection_warning)

    warnings.extend(
        check_quality(avg_chars_per_page=avg_chars_per_page, image_count=image_count, total_pages=total_pages)
    )

    duplicate = await find_near_duplicate(
        session, course_id=course_id, new_embedding=document_embedding, exclude_document_id=exclude_document_id
    )
    if duplicate is not None:
        warnings.append(
            f"⚠️ Nội dung giống {duplicate.similarity:.0%} với tài liệu đã có "
            f"'{duplicate.title}' (#{duplicate.document_id}) - kiểm tra có phải trùng lặp không."
        )

    return CuratorReport(notes="\n".join(warnings) if warnings else None)
