"""
Điểm khởi động của Backend (bộ não xử lý của Academic Assistant).

File này là nơi FastAPI "sống" - mọi request từ frontend (trình duyệt của
người dùng) sẽ đi qua đây trước tiên. Các nhóm endpoint theo chủ đề (auth,
courses...) được viết ở file riêng rồi "gắn" (include_router) vào đây -
giữ file này gọn, chỉ đóng vai trò lắp ráp.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic_agent.feedback_router import router as feedback_router
from app.academic_agent.router import router as chat_router
from app.auth.router import router as auth_router
from app.config import get_settings
from app.courses.router import router as courses_router
from app.connectors.router import router as connectors_router
from app.db.session import get_db
from app.documents.router import router as documents_router
from app.eval_dashboard.router import router as eval_dashboard_router
from app.guardrail.router import router as guardrail_router
from app.instructor.router import router as instructor_router
from app.internal_learning.router import router as internal_learning_router
from app.learning.assignment_router import quiz_questions_router, router as assignment_router
from app.voice.router import router as voice_router
from app.learning.router import router as learning_router
from app.logging_config import configure_logging
from app.profile.router import router as profile_router
from app.personalization.router import memory_router, router as personalization_router
from app.operations.router import router as operations_router
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.request_id_middleware import RequestIdMiddleware
from app.retrieval.router import chunks_router, router as retrieval_router
from app.router_agent.router import router as router_agent_router

configure_logging()


def _warm_up_openai_sdk_imports() -> None:
    """
    "Chạm" vào các thuộc tính lazy-load của OpenAI SDK (.chat,
    .moderations, .embeddings) NGAY LÚC KHỞI ĐỘNG, tuần tự trong 1
    thread duy nhất - PHÁT HIỆN QUA LỖI THẬT: openai-python dùng
    functools.cached_property để hoãn import các submodule con
    (openai.resources.chat, .moderations...) tới lần đầu tiên được
    truy cập, thay vì import hết ngay khi import openai.

    Nếu 2 THREAD KHÁC NHAU (từ app/guardrail/, app/router_agent/,
    app/academic_agent/ - mỗi module có 1 OpenAI() client riêng) cùng
    lần đầu truy cập các thuộc tính này GẦN NHƯ ĐỒNG THỜI (đúng tình
    huống asyncio.gather() chạy Guardrail + Router song song), Python
    import lock có thể DEADLOCK - đã tái hiện được lỗi này bằng
    _frozen_importlib._DeadlockError khi đo tốc độ streaming thật.

    Gọi từng client.chat/.moderations/.embeddings 1 LẦN, TUẦN TỰ, ngay
    khi module này được import (trước khi bất kỳ request nào tới) -
    sau lần đầu, Python cache lại kết quả (cached_property), các lần
    truy cập sau (kể cả từ nhiều thread song song) không còn phải
    import gì nữa, không còn nguy cơ deadlock.
    """
    from app.academic_agent.agent import _client as academic_client
    from app.guardrail.moderation import _client as moderation_client
    from app.ingestion.embedder import _client as embedder_client
    from app.learning.quiz_generator import _client as quiz_client
    from app.router_agent.classifier import _client as router_client

    for client in (academic_client, moderation_client, embedder_client, router_client, quiz_client):
        client.chat
        client.moderations
        client.embeddings


_warm_up_openai_sdk_imports()

app = FastAPI(
    title="Academic Assistant API",
    description="Backend cho hệ thống Trợ lý Học thuật đa agent",
    version="0.1.0",
)

# Request ID PHẢI được gắn TRƯỚC (ngoài cùng) mọi middleware khác -
# Starlette chạy middleware theo thứ tự khai báo NGƯỢC (middleware
# thêm sau cùng chạy TRƯỚC TIÊN) - đặt add_middleware này trước
# CORSMiddleware bên dưới nghĩa là request_id có sẵn sớm nhất có thể,
# để cả những lỗi xảy ra ở tầng CORS cũng được log kèm đúng id.
app.add_middleware(RequestIdMiddleware)

# Rate limiting: gắn limiter vào app + đăng ký handler xử lý khi vượt
# giới hạn (tự động trả lỗi 429 "Too Many Requests" đúng chuẩn HTTP
# thay vì để lỗi rơi tự do).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: chỉ các domain trong danh sách whitelist (config.cors_allowed_origins)
# mới được trình duyệt cho phép gọi API này bằng JavaScript. Đây là
# điều BẮT BUỘC phải có trước khi frontend (chạy ở domain khác - vd
# Vercel) gọi vào backend (vd Fly.io) - không có middleware này, trình
# duyệt sẽ tự chặn mọi request cross-origin, kể cả khi cả 2 phía code
# đều đúng.
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allowed_origins_list,
    allow_credentials=True,  # BẮT BUỘC để cookie (JWT) được gửi kèm qua cross-origin request
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(connectors_router)
app.include_router(documents_router)
app.include_router(retrieval_router)
app.include_router(chunks_router)
app.include_router(guardrail_router)
app.include_router(router_agent_router)
app.include_router(chat_router)
app.include_router(feedback_router)
app.include_router(learning_router)
app.include_router(assignment_router)
app.include_router(quiz_questions_router)
app.include_router(instructor_router)
app.include_router(internal_learning_router)
app.include_router(eval_dashboard_router)
app.include_router(profile_router)
app.include_router(personalization_router)
app.include_router(memory_router)
app.include_router(operations_router)
app.include_router(voice_router)


@app.get("/healthz")
def health_check():
    """
    Endpoint kiểm tra "sức khỏe" server.

    Trả về gì: một JSON đơn giản báo server đang chạy tốt.
    Ai gọi nó: hệ thống hạ tầng (Fly.io), không phải người dùng cuối.
    """
    return {"status": "ok", "service": "academic-assistant-api"}


@app.get("/healthz/db")
async def health_check_db(session: AsyncSession = Depends(get_db)):
    """
    Kiểm tra backend có kết nối được tới Database không.

    Khác với /healthz (chỉ kiểm tra server sống), endpoint này thực sự
    gửi 1 câu lệnh nhỏ nhất có thể ("SELECT 1") tới Postgres và chờ
    phản hồi - nếu DATABASE_URL sai hoặc Neon chưa bật, endpoint này
    sẽ báo lỗi rõ ràng thay vì để lỗi xuất hiện âm thầm ở tính năng
    khác về sau.
    """
    result = await session.execute(text("SELECT 1"))
    return {"status": "ok", "db_check": result.scalar()}


@app.get("/")
def root():
    """Trang gốc - chỉ để xác nhận server chạy khi bạn mở link trên trình duyệt."""
    return {
        "message": "Academic Assistant API đang chạy.",
        "docs": "/docs",  # FastAPI tự sinh trang tài liệu API tương tác tại đây
    }
