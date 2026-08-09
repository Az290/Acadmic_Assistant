"""
Endpoint test độc lập cho Router Agent - cùng lý do với Guardrail
(app/guardrail/router.py): Academic Agent (Tác vụ #8) chưa tồn tại để
tích hợp trực tiếp, endpoint này cho phép kiểm chứng logic phân loại
qua HTTP thật ngay bây giờ.
"""

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import get_current_user
from app.db.models import AppUser
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.router_agent.classifier import classify
from app.router_agent.schemas import RouteClassifyRequest, RouteClassifyResponse

router = APIRouter(prefix="/v1/route", tags=["router-agent"])


@router.post("/classify", response_model=RouteClassifyResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def route_classify(
    request: Request,
    body: RouteClassifyRequest,
    user: AppUser = Depends(get_current_user),
):
    """
    Phân loại 1 câu hỏi vào 1 trong 4 danh mục (RAG_QUESTION,
    SOCRATIC_REQUEST, CHITCHAT, OFF_TOPIC) - quyết định có cần chạy
    Hybrid Search trước khi trả lời hay không.
    """
    result = classify(body.text)
    return RouteClassifyResponse(
        category=result.category,
        reasoning=result.reasoning,
        needs_retrieval=result.needs_retrieval,
        classified_by=result.classified_by,
    )
