"""
Endpoint upload tài liệu - nơi giáo viên đưa 1 file PDF vào hệ thống,
kích hoạt toàn bộ Ingestion Pipeline: Parse -> Chunk -> Embed -> Lưu Database.
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AppUser, Course, Document, Enrollment
from app.db.session import get_db
from app.documents.schemas import DocumentContent, DocumentContentChunk, DocumentPublic, DocumentSummary
from app.documents.validation import (
    validate_file_size,
    validate_pdf_magic_bytes,
    validate_upload_filename,
)
from app.ingestion.pipeline import ingest_document
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.retrieval.access_policy import chunk_access_sql

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


@router.get("", response_model=list[DocumentSummary])
async def list_documents(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Liệt kê tài liệu ĐÃ DUYỆT của 1 lớp - đây là chỗ sinh viên tự XEM
    LẠI được tài liệu (trước đây trang "Tài liệu" chỉ có upload, sinh
    viên hoàn toàn không có cách nào biết lớp có kiến thức gì để hỏi Nova).

    RBAC: CỐ Ý KHÔNG dùng _require_course_owner() của app/instructor/
    router.py (hàm đó CHỈ cho chủ lớp/ADMIN đi qua) - ở đây SINH VIÊN
    đang enroll lớp cũng phải gọi được, nên viết kiểm tra riêng: chủ lớp
    HOẶC ADMIN HOẶC đang enroll.

    Chỉ trả tài liệu mà người gọi đọc được ÍT NHẤT 1 chunk (chunk_count
    > 0 sau khi lọc theo chunk_access_sql()) - tránh hiện tài liệu toàn
    INSTRUCTOR_ONLY cho sinh viên rồi họ bấm "Đọc nội dung" ra màn hình
    trống, gây khó hiểu không cần thiết.
    """
    course_result = await session.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lớp này.")

    is_owner = course.owner_id == user.id or user.role == "ADMIN"
    if not is_owner:
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

    result = await session.execute(
        text(
            f"""
            SELECT
                document.id AS id,
                document.title AS title,
                document.created_at AS created_at,
                document.image_count AS image_count,
                app_user.full_name AS uploaded_by_name,
                COUNT(chunk.id) AS chunk_count
            FROM document
            JOIN app_user ON app_user.id = document.uploaded_by
            JOIN chunk ON chunk.document_id = document.id AND {chunk_access_sql()}
            WHERE document.course_id = :course_id
              AND document.status = 'APPROVED'
            GROUP BY document.id, document.title, document.created_at,
                     document.image_count, app_user.full_name
            HAVING COUNT(chunk.id) > 0
            ORDER BY document.created_at DESC
            """
        ),
        {"course_id": course_id, "user_id": user.id, "is_admin": user.role == "ADMIN"},
    )
    rows = result.all()
    return [
        DocumentSummary(
            id=row.id,
            title=row.title,
            created_at=row.created_at.isoformat(),
            image_count=row.image_count,
            chunk_count=row.chunk_count,
            uploaded_by_name=row.uploaded_by_name,
        )
        for row in rows
    ]


@router.get("/{document_id}/content", response_model=DocumentContent)
async def get_document_content(
    document_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Trả TOÀN BỘ nội dung (chunk) mà người gọi ĐƯỢC PHÉP ĐỌC của 1 tài
    liệu, theo đúng thứ tự (chunk.ord) - dùng khi sinh viên bấm "Đọc
    nội dung" trên trang Tài liệu để thực sự học từ tài liệu của lớp,
    không chỉ upload rồi không bao giờ xem lại.

    ÁP DỤNG ĐÚNG chunk_access_sql() như get_chunk_detail() ở
    app/retrieval/router.py - tài liệu chưa duyệt, hoặc chunk
    INSTRUCTOR_ONLY mà người gọi không có quyền, sẽ tự động không xuất
    hiện trong kết quả.

    Trả 404 (KHÔNG PHẢI 403) khi không đọc được chunk nào - giống hệt
    lý do ở get_chunk_detail(): không tiết lộ cho người dò id liệu tài
    liệu này có tồn tại hay không, hay chỉ đơn giản là họ không có quyền.

    GHI CHÚ: KHÔNG phân trang ở bản này - tài liệu thường chỉ vài chục
    tới vài trăm chunk, chấp nhận được. Nếu sau này có tài liệu rất lớn
    (hàng nghìn chunk) thì ĐÂY LÀ CHỖ cần thêm limit/offset.
    """
    result = await session.execute(
        text(
            f"""
            SELECT
                chunk.id AS chunk_id,
                chunk.ord AS ord,
                chunk.page_number AS page_number,
                chunk.content AS content,
                chunk.content_type AS content_type,
                chunk.context_prefix AS context_prefix,
                document.title AS document_title
            FROM chunk
            JOIN document ON document.id = chunk.document_id
            WHERE chunk.document_id = :document_id
              AND {chunk_access_sql()}
            ORDER BY chunk.ord
            """
        ),
        {"document_id": document_id, "user_id": user.id, "is_admin": user.role == "ADMIN"},
    )
    rows = result.all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài liệu này."
        )

    return DocumentContent(
        document_id=document_id,
        title=rows[0].document_title,
        total_chunks=len(rows),
        chunks=[
            DocumentContentChunk(
                chunk_id=row.chunk_id,
                ord=row.ord,
                page_number=row.page_number,
                content=row.content,
                content_type=row.content_type,
                context_prefix=row.context_prefix,
            )
            for row in rows
        ],
    )


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Trả về FILE PDF GỐC để người học đọc trực tiếp trong trình duyệt.

    TẠI SAO CẦN: trước đây sinh viên chỉ xem được nội dung đã CHUNK
    (cắt nhỏ theo đoạn, mất bố cục, mất hình/bảng, xuống dòng lộn xộn)
    - đó là định dạng phục vụ MÁY tra cứu, người đọc gần như không hiểu
    gì. Muốn thực sự HỌC thì phải đọc bản gốc.

    Quyền: giống hệt list_documents() - chủ lớp/ADMIN, hoặc sinh viên
    đang enroll lớp chứa tài liệu. Thêm ràng buộc tài liệu phải
    APPROVED (tài liệu chờ duyệt chỉ giảng viên xem qua trang Duyệt
    tài liệu, không phát tán cho sinh viên qua đường này).

    Trả 404 chung cho MỌI trường hợp không được phép/không tồn tại -
    không tiết lộ tài liệu có tồn tại hay không cho người không có quyền.
    """
    result = await session.execute(
        select(Document, Course).join(Course, Course.id == Document.course_id).where(
            Document.id == document_id
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài liệu này.")

    document, course = row

    is_owner = course.owner_id == user.id or user.role == "ADMIN"
    if not is_owner:
        enrolled = await session.execute(
            select(Enrollment).where(
                Enrollment.user_id == user.id, Enrollment.course_id == course.id
            )
        )
        if enrolled.scalar_one_or_none() is None or document.status != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài liệu này."
            )

    # storage_uri hiện là đường dẫn file trên đĩa cục bộ (xem UPLOAD_DIR
    # ở đầu file) - khi chuyển sang Object Storage thật thì ĐÂY là chỗ
    # đổi sang redirect tới signed URL, phần kiểm tra quyền ở trên giữ nguyên.
    file_path = Path(document.storage_uri)
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File gốc không còn trên máy chủ (có thể đã bị xoá khi khởi động lại).",
        )

    # inline: mở thẳng trong tab/iframe trình duyệt thay vì tải về máy -
    # đúng mục đích "đọc để học", không phải "tải tài liệu về".
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=document.title,
        content_disposition_type="inline",
    )
