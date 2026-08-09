"""
Endpoint test độc lập cho Guardrail - Academic Agent (Tác vụ #8) CHƯA
tồn tại để tích hợp trực tiếp, endpoint này cho phép kiểm chứng logic
guardrail qua HTTP thật ngay bây giờ, và sẽ được Agent gọi làm bước
tiền xử lý khi Agent được xây.
"""

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import get_current_user
from app.db.models import AppUser
from app.guardrail.guardrail import check_input, check_output
from app.guardrail.schemas import GuardrailCheckRequest, GuardrailCheckResponse
from app.rate_limit import DEFAULT_RATE_LIMIT, limiter

router = APIRouter(prefix="/v1/guardrail", tags=["guardrail"])


@router.post("/check", response_model=GuardrailCheckResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def guardrail_check(
    request: Request,
    body: GuardrailCheckRequest,
    user: AppUser = Depends(get_current_user),
):
    """
    Kiểm tra 1 đoạn text qua guardrail - direction="input" dùng luồng
    kiểm tra câu hỏi user, direction="output" dùng luồng kiểm tra câu
    trả lời AI (không chạy rule-based injection, xem guardrail.py).
    """
    check_fn = check_input if body.direction == "input" else check_output
    result = check_fn(body.text)
    return GuardrailCheckResponse(allowed=result.allowed, reason=result.reason, blocked_by=result.blocked_by)
