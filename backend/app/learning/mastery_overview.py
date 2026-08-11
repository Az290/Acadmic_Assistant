"""
Logic TÍNH TOÁN dùng chung cho mọi tính năng cần biết "sinh viên đang
yếu ở khái niệm nào" - hiện có 2 nơi dùng:

1. Proactive AI Toast (app/learning/router.py::get_weakest_concept) -
   cần ĐÚNG 1 khái niệm yếu nhất để nhắc chủ động.
2. Trang Tiến độ học tập (app/learning/router.py::get_mastery_overview) -
   cần TOÀN BỘ danh sách để hiển thị "Gợi ý ôn tập".

Tách hàm domain riêng ở đây (không đặt trong router.py) để 2 endpoint
trên chỉ khác nhau ở cách CẮT kết quả, không viết lại truy vấn SQL và
điều kiện lọc 2 lần - tránh 2 nơi dần lệch nhau khi sau này chỉnh sửa
điều kiện lọc.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept, Enrollment, StudentMastery

# Ngưỡng phân loại HIỂN THỊ (LOW/MID/HIGH) - THỐNG NHẤT TOÀN HỆ THỐNG,
# nhưng KHÁC với ngưỡng TRIGGER của Proactive Toast (accuracy < 50%,
# xem get_weakest_concept()). Đây là 2 khái niệm khác nhau có chủ ý:
# - Ngưỡng phân loại: dùng để TÔ MÀU trên trang Tiến độ (khi nào đỏ/
#   vàng/xanh).
# - Ngưỡng trigger Toast: dùng để QUYẾT ĐỊNH có làm phiền sinh viên
#   bằng 1 thông báo chủ động hay không - cố ý giữ NGHIÊM NGẶT hơn
#   (50% thay vì 40%) để tránh nhắc quá thường xuyên.
MASTERY_LOW_THRESHOLD = 0.4
MASTERY_HIGH_THRESHOLD = 0.7


@dataclass
class WeakConcept:
    concept_id: int
    concept_name: str
    course_id: int
    n_obs: int
    n_correct: int
    accuracy: float


async def compute_weak_concepts(session: AsyncSession, *, user_id: int) -> list[WeakConcept]:
    """
    Trả về TOÀN BỘ concept CHƯA mastered mà sinh viên đã có ít nhất 1
    lượt quan sát (n_obs >= 1), sắp xếp accuracy TĂNG DẦN (yếu nhất
    đứng đầu). KHÔNG lọc theo ngưỡng accuracy < 50% ở đây - việc đó là
    quyết định RIÊNG của từng nơi gọi (Toast lọc <50%, trang Tiến độ
    hiển thị TẤT CẢ chưa mastered để sinh viên tự thấy toàn cảnh).
    """
    rows = (
        await session.execute(
            select(StudentMastery, Concept.name, Concept.course_id)
            .join(Concept, Concept.id == StudentMastery.concept_id)
            .join(Enrollment, (Enrollment.course_id == Concept.course_id) & (Enrollment.user_id == user_id))
            .where(StudentMastery.user_id == user_id, StudentMastery.n_obs >= 1, StudentMastery.mastered.is_(False))
        )
    ).all()

    weak = [
        WeakConcept(
            concept_id=mastery.concept_id,
            concept_name=concept_name,
            course_id=course_id,
            n_obs=mastery.n_obs,
            n_correct=mastery.n_correct,
            accuracy=mastery.n_correct / mastery.n_obs,
        )
        for mastery, concept_name, course_id in rows
    ]
    # accuracy thấp nhất trước, hoà thì n_obs lớn hơn trước (đáng tin hơn).
    weak.sort(key=lambda w: (w.accuracy, -w.n_obs))
    return weak
