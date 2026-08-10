"""
Cập nhật mức độ nắm vững (StudentMastery) theo chiến lược HEURISTIC -
xem docstring model StudentMastery (app/db/models.py) để hiểu vì sao
không dùng BKT thật ở giai đoạn này.

Luật đơn giản, có chủ đích minh bạch (không phải "hộp đen"):
- Trả lời ĐÚNG: streak += 1. Đạt streak >= MASTERY_STREAK_THRESHOLD -> mastered = True.
- Trả lời SAI: streak reset về 0. mastered giữ nguyên (KHÔNG tự động
  "rút lại" trạng thái đã thành thạo chỉ vì 1 lần sai - tránh dao động
  qua lại gây khó hiểu cho người học, đúng tinh thần "mastery" là tích
  luỹ dài hạn, không phải điểm số tức thời).
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StudentMastery

MASTERY_STREAK_THRESHOLD = 3


async def get_or_create_mastery(session: AsyncSession, *, user_id: int, concept_id: int) -> StudentMastery:
    result = await session.execute(
        select(StudentMastery).where(
            StudentMastery.user_id == user_id, StudentMastery.concept_id == concept_id
        )
    )
    mastery = result.scalar_one_or_none()
    if mastery is not None:
        return mastery

    mastery = StudentMastery(user_id=user_id, concept_id=concept_id)
    session.add(mastery)
    await session.flush()
    return mastery


def apply_answer(mastery: StudentMastery, *, is_correct: bool) -> None:
    """
    Cập nhật TRỰC TIẾP đối tượng mastery (đã có sẵn trong session, chưa
    commit) - tách hàm thuần logic này riêng khỏi router.py để dễ đọc/
    test độc lập, không lẫn với việc truy vấn DB.
    """
    mastery.n_obs += 1
    mastery.last_seen_at = datetime.now(timezone.utc)

    if is_correct:
        mastery.n_correct += 1
        mastery.streak += 1
        if mastery.streak >= MASTERY_STREAK_THRESHOLD:
            mastery.mastered = True
    else:
        mastery.streak = 0
