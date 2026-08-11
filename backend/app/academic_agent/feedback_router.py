"""
Sinh viên đánh giá câu trả lời của AI là hữu ích (👍) hay không (👎).

VÌ SAO CẦN: mọi chỉ số máy tự đo (độ khớp tài liệu, số trích dẫn...)
đều chỉ đo được QUÁ TRÌNH, không đo được KẾT QUẢ có thực sự giúp người
học hay không. Feedback từ chính người dùng là tín hiệu chất lượng
đáng tin nhất, và là dữ liệu đầu vào cho trang "Câu hỏi phổ biến" của
giảng viên (biết chủ đề nào kho tài liệu đang đáp ứng kém).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AppUser, Conversation, Message, MessageFeedback
from app.db.session import get_db
from app.academic_agent.feedback_schemas import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/v1/messages", tags=["feedback"])


@router.post("/{message_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    message_id: int,
    body: FeedbackRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Gửi/đổi đánh giá cho 1 câu trả lời. Gọi lại với giá trị khác = ĐỔI Ý
    (cập nhật dòng cũ), không tạo thêm dòng mới - khoá chính cặp
    (message_id, user_id) ở tầng database đảm bảo điều này kể cả khi
    2 request tới gần như đồng thời.

    CHỈ đánh giá được tin nhắn TRONG HỘI THOẠI CỦA CHÍNH MÌNH: kiểm tra
    qua Conversation.user_id chứ không tin tham số client gửi lên - nếu
    không, bất kỳ ai cũng có thể gọi thẳng API để bỏ phiếu hàng loạt
    lên hội thoại của người khác, làm sai lệch thống kê của giảng viên.
    """
    message = (
        await session.execute(
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Message.id == message_id, Conversation.user_id == user.id)
        )
    ).scalar_one_or_none()

    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy câu trả lời này trong hội thoại của bạn.",
        )

    if message.role != "assistant":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ đánh giá được câu trả lời của trợ lý, không phải câu hỏi của chính bạn.",
        )

    existing = (
        await session.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == message_id, MessageFeedback.user_id == user.id
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        session.add(MessageFeedback(message_id=message_id, user_id=user.id, is_positive=body.is_positive))
    else:
        existing.is_positive = body.is_positive

    try:
        await session.commit()
    except IntegrityError:
        # 2 request đồng thời (vd bấm 👍 rồi đổi 👎 thật nhanh, hoặc
        # double-click) cùng thấy existing=None rồi cùng INSERT - khoá
        # chính cặp chặn dòng thứ hai. Rollback rồi UPDATE dòng mà
        # request kia vừa tạo, để kết quả cuối cùng vẫn đúng ý người
        # dùng thay vì báo lỗi cho 1 thao tác hoàn toàn hợp lệ.
        await session.rollback()
        existing = (
            await session.execute(
                select(MessageFeedback).where(
                    MessageFeedback.message_id == message_id, MessageFeedback.user_id == user.id
                )
            )
        ).scalar_one()
        existing.is_positive = body.is_positive
        await session.commit()

    return FeedbackResponse(message_id=message_id, is_positive=body.is_positive)
