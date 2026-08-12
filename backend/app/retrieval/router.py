"""
Endpoint tìm kiếm - lớp API mỏng gọi vào app/retrieval/hybrid_search.py.

Đây là mảnh ghép RAG đầu tiên có thể gọi thật qua HTTP: nhận 1 câu hỏi,
trả về những đoạn tài liệu liên quan nhất mà user được phép thấy. Bước
tiếp theo (Agent) sẽ dùng CHÍNH kết quả này làm "ngữ cảnh" đưa cho LLM
trước khi LLM soạn câu trả lời cuối - endpoint này CHƯA gọi LLM, chỉ
làm phần tìm kiếm.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AppUser
from app.db.session import get_db
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.retrieval.access_policy import chunk_access_sql
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.schemas import ChunkDetail, SearchRequest, SearchResponse

router = APIRouter(prefix="/v1/search", tags=["search"])

# Router thứ 2 với prefix khác - cùng module vì cùng chủ đề (đọc dữ
# liệu tài liệu) và dùng CHUNG một bộ lọc quyền truy cập.
chunks_router = APIRouter(prefix="/v1/chunks", tags=["chunks"])


@router.post("", response_model=SearchResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def search(
    request: Request,
    body: SearchRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Tìm kiếm hybrid (vector + full-text + RRF), tự động giới hạn trong
    những course mà user đang đăng nhập được enroll - không cần
    truyền course_id, quyền truy cập được xác định hoàn toàn từ
    danh tính user (đọc trong hybrid_search.py).

    @limiter.limit(DEFAULT_RATE_LIMIT): mỗi lần gọi tốn 1 lượt gọi
    OpenAI embedding THẬT (chi phí thật, không phải chỉ tốn CPU nội
    bộ) - không giới hạn tần suất nghĩa là 1 user có thể spam gọi để
    tiêu tốn ngân sách API vô tội vạ, hoặc vô tình/cố ý gây quá tải
    cho cả embedding API lẫn Postgres. `request: Request` là tham số
    bắt buộc để slowapi đọc được địa chỉ IP người gọi.
    """
    results = await hybrid_search(
        session, query_text=body.query, user_id=user.id, is_admin=user.role == "ADMIN"
    )
    return SearchResponse(query=body.query, results=results)


@chunks_router.get("/{chunk_id}", response_model=ChunkDetail)
async def get_chunk_detail(
    chunk_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Đọc nguyên văn 1 đoạn tài liệu - dùng khi người học bấm vào badge
    trích dẫn [#41] trong câu trả lời để xem AI đã dựa vào đoạn nào.

    ÁP DỤNG ĐÚNG BỘ LỌC QUYỀN của Hybrid Search (chunk phải thuộc lớp
    user đã enroll, không phải lời giải, tài liệu đã được duyệt). Đây
    là điều BẮT BUỘC chứ không phải tuỳ chọn: endpoint này cho phép đọc
    nội dung theo id, nếu thiếu bộ lọc thì bất kỳ ai cũng có thể dò id
    tuần tự (1, 2, 3...) để moi toàn bộ tài liệu của mọi lớp trong hệ
    thống - kể cả lớp họ không tham gia.

    Trả 404 (không phải 403) khi không có quyền: không tiết lộ cho
    người dò biết chunk đó có tồn tại hay không.
    """
    result = await session.execute(
        text(
            f"""
            SELECT chunk.id, chunk.content, chunk.page_number, document.title AS document_title
            FROM chunk
            JOIN document ON document.id = chunk.document_id
            WHERE chunk.id = :chunk_id
              AND {chunk_access_sql()}
            """
        ),
        {"chunk_id": chunk_id, "user_id": user.id, "is_admin": user.role == "ADMIN"},
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đoạn tài liệu này."
        )

    return ChunkDetail(
        chunk_id=row.id,
        content=row.content,
        page_number=row.page_number,
        document_title=row.document_title,
    )
