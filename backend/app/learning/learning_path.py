"""
Learning Path API - Lấy lộ trình học tập cho sinh viên trong 1 course.

Logic:
1. Lấy danh sách concepts trong course (đã có sẵn)
2. Lấy mastery data của sinh viên cho từng concept
3. Build dependency graph (nếu có prerequisites)
4. Xác định status:
   - completed: mastery > 0.8 (hoặc streak >= MASTERY_STREAK_THRESHOLD)
   - in_progress: 0.2 < mastery <= 0.8
   - available: chưa học, prerequisites đã completed
   - locked: chưa học, prerequisites chưa completed
5. Gợi ý concept tiếp theo nên học

Phân biệt với các endpoint khác trong hệ thống:
- /v1/learn/mastery: xem mastery CHI TIẾT (streak, n_obs, n_correct) cho 1 course
- /v1/learn/mastery/overview: TỔNG QUAN mọi course
- /v1/learn/weakest-concept: khái niệm yếu NHẤT cho Toast
- /v1/learning-path: LỘ TRÌNH học tập với dependency graph
"""

import json
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept, Course, Enrollment, StudentMastery


class ConceptStatus(str, Enum):
    COMPLETED = "completed"   # mastery > 0.8 hoặc đã mastered
    IN_PROGRESS = "in_progress"  # 0.2 < mastery <= 0.8
    AVAILABLE = "available"   # chưa học, prerequisites đã completed
    LOCKED = "locked"        # chưa học, prerequisites chưa completed
    NOT_STARTED = "not_started"  # chưa học, không có prerequisites


# Ngưỡng mastery
MASTERY_COMPLETED_THRESHOLD = 0.8
MASTERY_IN_PROGRESS_LOW = 0.2
MASTERY_IN_PROGRESS_HIGH = 0.8


@dataclass
class ConceptProgress:
    """Tiến độ của 1 concept trong learning path."""
    id: int
    name: str
    complexity: int
    mastery: float | None  # None = chưa có dữ liệu
    status: ConceptStatus
    prerequisites: list[int]
    estimated_time_minutes: int  # ước tính dựa trên complexity


@dataclass
class Recommendation:
    """Gợi ý cho sinh viên."""
    type: str  # "next_learn" | "review"
    concept_id: int
    concept_name: str
    reason: str
    priority: int  # 1 = cao nhất


@dataclass
class LearningPathResponse:
    """Response cho learning path endpoint."""
    course_id: int
    course_name: str
    concepts: list[ConceptProgress]
    recommendations: list[Recommendation]


def _parse_prerequisites(prerequisites_field) -> list[int]:
    """Parse prerequisites từ JSON string hoặc list."""
    if not prerequisites_field:
        return []
    if isinstance(prerequisites_field, list):
        return prerequisites_field
    if isinstance(prerequisites_field, str):
        try:
            parsed = json.loads(prerequisites_field)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _calculate_mastery(mastery_row: StudentMastery | None) -> float | None:
    """Tính mastery percentage từ StudentMastery row."""
    if mastery_row is None:
        return None
    if mastery_row.n_obs == 0:
        return None
    return mastery_row.n_correct / mastery_row.n_obs


def _estimate_time_minutes(complexity: int, mastery: float | None) -> int:
    """Ước tính thời gian học dựa trên complexity và mastery hiện tại."""
    base_time = {
        1: 15,
        2: 25,
        3: 40,
        4: 60,
        5: 90,
    }.get(complexity, 40)

    if mastery is None:
        return base_time
    if mastery >= MASTERY_COMPLETED_THRESHOLD:
        return max(5, int(base_time * 0.2))  # Ôn tập nhanh
    if mastery >= MASTERY_IN_PROGRESS_LOW:
        return int(base_time * (1 - mastery))  # Càng yếu càng cần nhiều thời gian
    return base_time


def _determine_status(
    concept: Concept,
    mastery_row: StudentMastery | None,
    completed_ids: set[int],
    in_progress_ids: set[int],
) -> ConceptStatus:
    """Xác định status của 1 concept."""
    mastery = _calculate_mastery(mastery_row)

    # Đã mastered hoặc mastery cao
    if mastery_row is not None and (mastery_row.mastered or (mastery is not None and mastery > MASTERY_COMPLETED_THRESHOLD)):
        return ConceptStatus.COMPLETED

    # Đang học (có dữ liệu, đã bắt đầu nhưng chưa xong)
    if mastery is not None and MASTERY_IN_PROGRESS_LOW < mastery <= MASTERY_IN_PROGRESS_HIGH:
        return ConceptStatus.IN_PROGRESS

    # Chưa học - kiểm tra prerequisites
    if mastery is None or mastery <= MASTERY_IN_PROGRESS_LOW:
        prereqs = _parse_prerequisites(concept.prerequisites)

        if not prereqs:
            # Không có prerequisites - có thể học ngay
            return ConceptStatus.NOT_STARTED

        # Tất cả prerequisites đã completed -> available
        prereq_set = set(prereqs)
        if prereq_set.issubset(completed_ids):
            return ConceptStatus.AVAILABLE
        else:
            # Còn prerequisites chưa xong -> locked
            return ConceptStatus.LOCKED

    return ConceptStatus.NOT_STARTED


async def get_learning_path(
    session: AsyncSession,
    course_id: int,
    user_id: int,
) -> LearningPathResponse:
    """
    Lấy learning path cho sinh viên trong 1 course.

    Args:
        session: Database session
        course_id: ID của course
        user_id: ID của sinh viên

    Returns:
        LearningPathResponse với danh sách concepts và recommendations
    """
    # 1. Lấy thông tin course
    course_result = await session.execute(
        select(Course).where(Course.id == course_id)
    )
    course = course_result.scalar_one_or_none()
    if course is None:
        raise ValueError(f"Không tìm thấy course với id={course_id}")

    # 2. Kiểm tra enrollment
    enrollment_result = await session.execute(
        select(Enrollment).where(
            Enrollment.user_id == user_id,
            Enrollment.course_id == course_id
        )
    )
    if enrollment_result.scalar_one_or_none() is None:
        raise ValueError("Bạn chưa thuộc lớp học này.")

    # 3. Lấy tất cả concepts trong course
    concepts_result = await session.execute(
        select(Concept)
        .where(Concept.course_id == course_id)
        .order_by(Concept.complexity, Concept.name)
    )
    concepts = concepts_result.scalars().all()

    if not concepts:
        return LearningPathResponse(
            course_id=course_id,
            course_name=course.name,
            concepts=[],
            recommendations=[],
        )

    # 4. Lấy mastery data của sinh viên cho tất cả concepts
    concept_ids = [c.id for c in concepts]
    mastery_result = await session.execute(
        select(StudentMastery)
        .where(
            StudentMastery.user_id == user_id,
            StudentMastery.concept_id.in_(concept_ids)
        )
    )
    mastery_map: dict[int, StudentMastery] = {
        m.concept_id: m for m in mastery_result.scalars().all()
    }

    # 5. Build progress data cho từng concept
    concept_progress: list[ConceptProgress] = []
    completed_ids: set[int] = set()
    in_progress_ids: set[int] = set()

    # Lần đầu: xác định completed và in_progress
    for concept in concepts:
        mastery_row = mastery_map.get(concept.id)
        mastery = _calculate_mastery(mastery_row)

        if mastery_row is not None and (mastery_row.mastered or (mastery is not None and mastery > MASTERY_COMPLETED_THRESHOLD)):
            completed_ids.add(concept.id)
        elif mastery is not None and MASTERY_IN_PROGRESS_LOW < mastery <= MASTERY_IN_PROGRESS_HIGH:
            in_progress_ids.add(concept.id)

    # Lần hai: xác định status cho tất cả concepts
    for concept in concepts:
        mastery_row = mastery_map.get(concept.id)
        mastery = _calculate_mastery(mastery_row)
        status = _determine_status(concept, mastery_row, completed_ids, in_progress_ids)
        prerequisites = _parse_prerequisites(concept.prerequisites)

        concept_progress.append(ConceptProgress(
            id=concept.id,
            name=concept.name,
            complexity=concept.complexity,
            mastery=mastery,
            status=status,
            prerequisites=prerequisites,
            estimated_time_minutes=_estimate_time_minutes(concept.complexity, mastery),
        ))

    # 6. Tạo recommendations
    recommendations: list[Recommendation] = []

    # Ưu tiên 1: Gợi ý học khái niệm tiếp theo (in_progress -> available)
    for progress in concept_progress:
        if progress.status == ConceptStatus.IN_PROGRESS:
            # Đang học - gợi ý tiếp tục
            mastery_pct = int((progress.mastery or 0) * 100)
            recommendations.append(Recommendation(
                type="continue",
                concept_id=progress.id,
                concept_name=progress.name,
                reason=f"Đang học, tiến độ {mastery_pct}%",
                priority=1,
            ))

    # Ưu tiên 2: Gợi ý khái niệm available tiếp theo (prerequisites đã xong)
    available_concepts = [p for p in concept_progress if p.status == ConceptStatus.AVAILABLE]
    for i, progress in enumerate(available_concepts[:3]):  # Tối đa 3 gợi ý
        prereq_names = [
            c.name for c in concept_progress
            if c.id in progress.prerequisites
        ]
        prereq_text = ", ".join(prereq_names) if prereq_names else "đã hoàn thành"
        recommendations.append(Recommendation(
            type="next_learn",
            concept_id=progress.id,
            concept_name=progress.name,
            reason=f"Prerequisites {prereq_text}",
            priority=2 if i == 0 else 3,
        ))

    # Ưu tiên 3: Gợi ý ôn lại concept có mastery THẤP.
    #
    # KHÔNG lọc theo status == IN_PROGRESS - PHÁT HIỆN QUA TEST THẬT:
    # concept có mastery <= 0.2 (vd trả lời đúng 1/10) bị _determine_status
    # xếp vào NOT_STARTED, nên điều kiện cũ (chỉ xét IN_PROGRESS) không
    # bao giờ khớp - sinh viên YẾU NHẤT lại là người không nhận được gợi
    # ý ôn tập nào. Điều kiện đúng là "đã có dữ liệu làm bài (mastery
    # không None) và điểm còn thấp", không phụ thuộc nhãn status.
    low_mastery = [
        p for p in concept_progress
        if p.mastery is not None
        and p.mastery <= MASTERY_IN_PROGRESS_LOW
    ]
    for progress in low_mastery[:2]:  # Tối đa 2 gợi ý ôn tập
        recommendations.append(Recommendation(
            type="review",
            concept_id=progress.id,
            concept_name=progress.name,
            reason=f"Cần ôn lại, mastery {int((progress.mastery or 0) * 100)}%",
            priority=4,
        ))

    # Ưu tiên 3.5: Sinh viên CHƯA BẮT ĐẦU concept nào - gợi ý concept
    # dễ nhất để vào học. Nếu không có nhánh này, sinh viên mới (mọi
    # concept đều not_started) sẽ thấy màn hình gợi ý TRỐNG - đúng lúc
    # họ cần định hướng nhất. Chọn theo complexity tăng dần (concepts
    # đã được sắp xếp sẵn theo complexity, name ở bước truy vấn).
    if not recommendations:
        not_started = [p for p in concept_progress if p.status == ConceptStatus.NOT_STARTED]
        for i, progress in enumerate(not_started[:3]):
            recommendations.append(Recommendation(
                type="start_here",
                concept_id=progress.id,
                concept_name=progress.name,
                reason=f"Bắt đầu từ đây - độ khó {progress.complexity}/5, khoảng {progress.estimated_time_minutes} phút",
                priority=2 if i == 0 else 3,
            ))

    # Sắp xếp recommendations theo priority
    recommendations.sort(key=lambda r: r.priority)

    return LearningPathResponse(
        course_id=course_id,
        course_name=course.name,
        concepts=concept_progress,
        recommendations=recommendations,
    )
