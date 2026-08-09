"""
Endpoint tìm kiếm - lớp API mỏng gọi vào app/retrieval/hybrid_search.py.

Đây là mảnh ghép RAG đầu tiên có thể gọi thật qua HTTP: nhận 1 câu hỏi,
trả về những đoạn tài liệu liên quan nhất mà user được phép thấy. Bước
tiếp theo (Agent) sẽ dùng CHÍNH kết quả này làm "ngữ cảnh" đưa cho LLM
trước khi LLM soạn câu trả lời cuối - endpoint này CHƯA gọi LLM, chỉ
làm phần tìm kiếm.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AppUser
from app.db.session import get_db
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/v1/search", tags=["search"])


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
    results = await hybrid_search(session, query_text=body.query, user_id=user.id)
    return SearchResponse(query=body.query, results=results)
