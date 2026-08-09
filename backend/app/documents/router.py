"""
Endpoint upload tài liệu - nơi giáo viên đưa 1 file PDF vào hệ thống,
kích hoạt toàn bộ Ingestion Pipeline: Parse -> Chunk -> Embed -> Lưu Database.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.db.models import AppUser, Course, Enrollment
from app.db.session import get_db
from app.documents.schemas import DocumentPublic
from app.documents.validation import (
    validate_file_size,
    validate_pdf_magic_bytes,
    validate_upload_filename,
)
from app.ingestion.pipeline import ingest_document
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter

router = APIRouter(prefix="/v1/documents", tags=["documents"])

# Nơi lưu file gốc TẠM THỜI trên đĩa cục bộ của server.
#
# Đây KHÔNG phải giải pháp lâu dài: khi deploy lên hạ tầng có container
# tự khởi động lại (vd Fly.io), đĩa cục bộ sẽ bị xoá mỗi lần restart -
# lúc đó cần chuyển sang Object Storage thật (vd Cloudflare R2) để lưu
# file bền vững, mà không cần sửa lại logic ingestion (chỉ đổi nơi lưu file).
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploaded_files"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload", response_model=DocumentPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def upload_document(
    request: Request,
    course_id: int,
    file: UploadFile,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Giáo viên upload 1 file PDF vào 1 lớp (course) cụ thể.

    Yêu cầu quyền: chỉ INSTRUCTOR sở hữu lớp đó (hoặc ADMIN) mới được
    upload - cùng nguyên tắc kiểm tra quyền đã dùng ở endpoint enroll,
    tránh giáo viên A tự ý thêm tài liệu vào lớp của giáo viên B.

    @limiter.limit(DEFAULT_RATE_LIMIT): mỗi lần upload chạy toàn bộ
    Ingestion Pipeline, gọi OpenAI embedding thật cho có thể hàng trăm
    chunk - không giới hạn tần suất để lộ khả năng double-click/script
    lỗi gọi liên tục làm tốn ngân sách API mà không có ai chặn lại.
    """
    course_result = await session.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lớp này.")

    if course.owner_id != user.id and user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không phải giáo viên phụ trách lớp này.",
        )

    # Thứ tự kiểm tra CÓ Ý NGHĨA: kiểm tra tên/định dạng rẻ nhất làm
    # trước, đọc toàn bộ nội dung file (tốn I/O) chỉ sau khi đã qua
    # được bước rẻ đó - tránh lãng phí công đọc file chắc chắn sẽ bị từ chối.
    validate_upload_filename(file.filename)

    file_bytes = await file.read()
    validate_file_size(file_bytes)
    validate_pdf_magic_bytes(file_bytes)

    # Đặt tên file lưu trên đĩa bằng UUID ngẫu nhiên (không dùng thẳng
    # tên gốc) - tránh 2 giáo viên cùng upload file trùng tên đè lên
    # nhau, và tránh ký tự lạ trong tên file gây lỗi hệ điều hành.
    stored_filename = f"{uuid.uuid4().hex}.pdf"
    stored_path = UPLOAD_DIR / stored_filename
    stored_path.write_bytes(file_bytes)

    try:
        document = await ingest_document(
            session,
            file_path=str(stored_path),
            file_bytes=file_bytes,
            title=file.filename,
            course_id=course_id,
            storage_uri=str(stored_path),
            uploaded_by=user.id,
        )
    except ValueError as e:
        # Ingestion thất bại vì lý do NGHIỆP VỤ đã lường trước (trùng
        # lặp, PDF rỗng...) - xoá file vừa lưu để không rác lại trên
        # đĩa, rồi trả lỗi rõ ràng, đúng thông điệp cho client.
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception:
        # Lỗi KHÔNG lường trước được (vd: PDF có đúng magic bytes
        # nhưng nội dung bị hỏng/mã hoá khiến PyMuPDF crash giữa
        # chừng) - vẫn phải dọn file rác, nhưng KHÔNG lộ chi tiết lỗi
        # kỹ thuật nội bộ ra ngoài cho client (rò rỉ thông tin hệ
        # thống) - chỉ trả thông điệp chung, đồng thời để lỗi gốc
        # tiếp tục "nổi" lên log server cho việc debug sau này.
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể xử lý file này - có thể file bị hỏng hoặc không đúng định dạng PDF chuẩn.",
        )

    return document
