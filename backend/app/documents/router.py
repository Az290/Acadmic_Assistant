"""
Endpoint upload tài liệu - nơi giáo viên đưa 1 file PDF vào hệ thống,
kích hoạt toàn bộ Ingestion Pipeline: Parse -> Chunk -> Embed -> Lưu Database.
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
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

logger = logging.getLogger(__name__)

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
    visibility: str = "COURSE",
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Đưa 1 file PDF vào 1 lớp (course) cụ thể.

    AI CÓ QUYỀN GỌI:
    - Giảng viên phụ trách lớp (hoặc ADMIN): upload tài liệu chính thức.
    - Sinh viên ĐANG HỌC lớp đó: ĐÓNG GÓP tài liệu (bài giảng chép tay,
      tài liệu tham khảo tự tìm...).

    An toàn của việc mở cho sinh viên nằm ở chỗ: MỌI tài liệu - bất kể
    ai upload - đều vào trạng thái PENDING_REVIEW và KHÔNG được Hybrid
    Search dùng cho tới khi giảng viên duyệt (xem
    app/ingestion/pipeline.py + app/retrieval/hybrid_search.py). Sinh
    viên không thể tự đẩy nội dung sai/độc hại vào câu trả lời của AI,
    vì luôn có người kiểm duyệt ở giữa. Curator Agent cũng tự quét chỉ
    dẫn ẩn trong file trước khi giảng viên xem.

    @limiter.limit(DEFAULT_RATE_LIMIT): mỗi lần upload chạy toàn bộ
    Ingestion Pipeline, gọi OpenAI embedding thật cho có thể hàng trăm
    chunk - không giới hạn tần suất để lộ khả năng double-click/script
    lỗi gọi liên tục làm tốn ngân sách API mà không có ai chặn lại.
    """
    course_result = await session.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lớp này.")

    is_owner = course.owner_id == user.id or user.role == "ADMIN"
    if not is_owner:
        # Không phải chủ lớp -> phải là người ĐANG HỌC lớp này mới được
        # đóng góp tài liệu. Người ngoài hoàn toàn không liên quan tới
        # lớp thì không có lý do gì được đẩy file vào.
        enrolled = await session.execute(
            select(Enrollment).where(
                Enrollment.user_id == user.id, Enrollment.course_id == course_id
            )
        )
        if enrolled.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không thuộc lớp học này.",
            )

    # Quyền truy cập nội dung sau khi tài liệu được duyệt:
    #   COURSE          - mọi người trong lớp đọc được (mặc định)
    #   INSTRUCTOR_ONLY - chỉ giảng viên của lớp + ADMIN (đề thi, đáp án)
    # Xem app/retrieval/access_policy.py để biết bộ lọc áp dụng thật sự.
    if visibility not in ("COURSE", "INSTRUCTOR_ONLY"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Quyền truy cập không hợp lệ.",
        )

    # CHẶN Ở TẦNG SERVER, không dựa vào việc giao diện có hiện ô chọn
    # hay không: nếu sinh viên đóng góp tài liệu được phép tự đánh dấu
    # INSTRUCTOR_ONLY, họ có thể đẩy nội dung vào kho mà chính bạn cùng
    # lớp không bao giờ tra cứu được - vừa vô nghĩa, vừa là kẽ hở để
    # giấu nội dung khỏi tầm kiểm soát thông thường.
    if visibility == "INSTRUCTOR_ONLY" and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ giảng viên phụ trách lớp mới đặt được quyền truy cập này.",
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
    # Ghi file tối đa 50MB (xem MAX_FILE_SIZE_BYTES) là I/O đồng bộ - đủ
    # lớn để đáng bọc asyncio.to_thread(), cùng lý do chặn event loop
    # như parse_pdf()/embed_texts() trong ingestion/pipeline.py.
    await asyncio.to_thread(stored_path.write_bytes, file_bytes)

    try:
        document = await ingest_document(
            session,
            file_path=str(stored_path),
            file_bytes=file_bytes,
            title=file.filename,
            course_id=course_id,
            storage_uri=str(stored_path),
            uploaded_by=user.id,
            visibility=visibility,
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
        # thống) - chỉ trả thông điệp chung.
        #
        # logger.exception() BẮT BUỘC ở đây - PHÁT HIỆN QUA LỖI THẬT:
        # trước đây comment nói "lỗi gốc tiếp tục nổi lên log" nhưng
        # KHÔNG CÓ dòng log nào thật sự - raise HTTPException() không
        # tự in traceback ra đâu cả (FastAPI xử lý HTTPException êm
        # xuôi, không coi là lỗi chưa bắt được), khiến nguyên nhân thật
        # (1 bug code thật ở Curator Agent) hoàn toàn biến mất khỏi log,
        # phải chạy lại thủ công ngoài server mới thấy được.
        stored_path.unlink(missing_ok=True)
        logger.exception("Lỗi không lường trước khi ingest tài liệu")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể xử lý file này - có thể file bị hỏng hoặc không đúng định dạng PDF chuẩn.",
        )

    return document
