"""Xác định vai trò Nova phải dùng trong ngữ cảnh lớp đang hoạt động."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Course, Enrollment


@dataclass(frozen=True)
class RoleContext:
    global_role: str
    effective_role: str
    course_id: int | None
    has_course_access: bool


async def resolve_role_context(
    session: AsyncSession,
    *,
    user_id: int,
    global_role: str,
    course_id: int | None,
) -> RoleContext:
    """Vai trò trong lớp thắng role toàn cục trong phạm vi lớp đó.

    Không có lớp thì giữ role toàn cục để dùng các năng lực hệ thống,
    nhưng caller không được nạp hồ sơ học tập của bất kỳ lớp nào.
    """
    if course_id is None:
        return RoleContext(global_role, global_role, None, False)

    owner_id = (
        await session.execute(select(Course.owner_id).where(Course.id == course_id))
    ).scalar_one_or_none()
    if owner_id is None:
        return RoleContext(global_role, "NONE", course_id, False)
    # Giao diện quản trị hiện là ngữ cảnh duy nhất của tài khoản ADMIN;
    # không suy diễn họ thành học viên chỉ vì có một enrollment cũ.
    if global_role == "ADMIN":
        return RoleContext(global_role, "ADMIN", course_id, True)
    if owner_id == user_id:
        return RoleContext(global_role, "INSTRUCTOR", course_id, True)

    enrollment_role = (
        await session.execute(
            select(Enrollment.role_in_course).where(
                Enrollment.course_id == course_id,
                Enrollment.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if enrollment_role in ("STUDENT", "INSTRUCTOR"):
        return RoleContext(global_role, enrollment_role, course_id, True)

    return RoleContext(global_role, "NONE", course_id, False)
