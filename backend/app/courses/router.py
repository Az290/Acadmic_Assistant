"""
3 endpoint hiện thực hoá ý tưởng "kênh riêng của giáo viên":
- Giáo viên tạo lớp (course)
- Giáo viên thêm học sinh vào lớp mình dạy (enrollment)
- Bất kỳ ai đăng nhập xem được danh sách lớp mình thuộc về

Đây chính là nền tảng ACL (phân quyền tài liệu): khi Ingestion và
Retrieval hoạt động, mọi câu truy vấn tìm tài liệu sẽ join qua bảng
`enrollment` để biết user được thấy course nào.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.courses.schemas import (
    CoursePublic,
    CreateCourseRequest,
    EnrollmentPublic,
    EnrollRequest,
    StudentRosterItem,
)
from app.db.models import AppUser, Course, Enrollment
from app.db.session import get_db

router = APIRouter(prefix="/v1/courses", tags=["courses"])


async def _require_course_owner(session: AsyncSession, *, user: AppUser, course_id: int) -> Course:
    """
    Kiểm tra "user có phải chủ lớp (hoặc ADMIN) không" - copy cùng
    pattern đã có ở app/instructor/router.py và
    app/learning/assignment_router.py (cùng tên hàm, KHÔNG import chéo
    giữa các module để tránh phụ thuộc chồng chéo không cần thiết -
    logic chỉ 5 dòng, trùng lặp ở đây rẻ hơn coupling 3 router lại).
    """
    result = await session.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lớp này.")

    if course.owner_id != user.id and user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không phải giáo viên phụ trách lớp này.",
        )
    return course


@router.post("", response_model=CoursePublic, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CreateCourseRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Giáo viên tạo 1 lớp/kênh mới. Người tạo tự động trở thành owner
    (dùng để kiểm tra quyền ở endpoint enroll bên dưới).

    Đồng thời tự thêm chính giáo viên vào bảng enrollment với vai trò
    INSTRUCTOR - để nhất quán logic: "muốn thấy/quản lý tài liệu của
    lớp nào, phải có 1 dòng enrollment ở lớp đó", kể cả với người tạo.
    """
    existing = await session.execute(select(Course).where(Course.code == body.code))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mã lớp này đã tồn tại.")

    course = Course(code=body.code, name=body.name, owner_id=user.id)
    session.add(course)
    try:
        await session.flush()  # để course.id có giá trị trước khi tạo enrollment bên dưới
    except IntegrityError:
        # Cùng lý do TOCTOU đã ghi ở register() - 2 giáo viên (hoặc 1
        # giáo viên double-click) tạo lớp trùng mã gần như đồng thời.
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mã lớp này đã tồn tại.")

    session.add(Enrollment(user_id=user.id, course_id=course.id, role_in_course="INSTRUCTOR"))
    await session.commit()
    await session.refresh(course)
    return course


@router.post("/{course_id}/enroll", response_model=EnrollmentPublic, status_code=status.HTTP_201_CREATED)
async def enroll_student(
    course_id: int,
    body: EnrollRequest,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Thêm 1 học sinh (theo email) vào lớp - chỉ CHÍNH giáo viên sở hữu
    lớp đó (hoặc ADMIN) mới được thêm, không phải bất kỳ INSTRUCTOR
    nào trong hệ thống (tránh giáo viên A thêm học sinh vào lớp của
    giáo viên B).
    """
    course_result = await session.execute(select(Course).where(Course.id == course_id))
    course = course_result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy lớp này.")

    if course.owner_id != user.id and user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không phải giáo viên phụ trách lớp này.",
        )

    student_result = await session.execute(select(AppUser).where(AppUser.email == body.student_email))
    student = student_result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy học sinh với email này - học sinh cần đăng ký tài khoản trước.",
        )

    already = await session.execute(
        select(Enrollment).where(
            Enrollment.user_id == student.id, Enrollment.course_id == course_id
        )
    )
    if already.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Học sinh này đã ở trong lớp.")

    enrollment = Enrollment(user_id=student.id, course_id=course_id, role_in_course="STUDENT")
    session.add(enrollment)
    try:
        await session.commit()
    except IntegrityError:
        # Cùng lý do TOCTOU - khoá chính CẶP (user_id, course_id) của
        # Enrollment tự nó đã là ràng buộc duy nhất, đủ để chặn 2 dòng
        # trùng lọt vào dù request đến gần như đồng thời.
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Học sinh này đã ở trong lớp.")
    return enrollment


@router.get("/me", response_model=list[CoursePublic])
async def list_my_courses(
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Danh sách lớp mà user hiện tại thuộc về (dù là học sinh hay giáo
    viên) - frontend dùng để hiển thị "Lớp của tôi" ngay sau đăng nhập.
    """
    result = await session.execute(
        select(Course).join(Enrollment, Enrollment.course_id == Course.id).where(
            Enrollment.user_id == user.id
        )
    )
    return result.scalars().all()


@router.get("/{course_id}/students", response_model=list[StudentRosterItem])
async def list_course_students(
    course_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Danh sách sinh viên đang học 1 lớp - CHỈ giáo viên chủ lớp (hoặc
    ADMIN) mới xem được (không phải mọi INSTRUCTOR trong hệ thống,
    cùng nguyên tắc đã áp dụng ở enroll_student()).

    Query tương tự pattern đã có ở app/instructor/router.py
    get_class_analytics() (join AppUser qua Enrollment, lọc
    role_in_course='STUDENT') - chỉ thêm email + joined_at vào SELECT.
    """
    await _require_course_owner(session, user=user, course_id=course_id)

    students = (
        await session.execute(
            select(AppUser.id, AppUser.full_name, AppUser.email, Enrollment.joined_at)
            .join(Enrollment, Enrollment.user_id == AppUser.id)
            .where(Enrollment.course_id == course_id, Enrollment.role_in_course == "STUDENT")
            .order_by(Enrollment.joined_at)
        )
    ).all()

    return [
        StudentRosterItem(user_id=row.id, full_name=row.full_name, email=row.email, enrolled_at=row.joined_at)
        for row in students
    ]


@router.delete("/{course_id}/students/{student_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_course_student(
    course_id: int,
    student_user_id: int,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(require_role("INSTRUCTOR", "ADMIN")),
):
    """
    Gỡ 1 sinh viên KHỎI LỚP - chỉ xoá dòng Enrollment (quan hệ "thuộc
    lớp nào"), KHÔNG đụng tới bất kỳ dữ liệu học tập nào khác của sinh
    viên (StudentMastery, Message, quiz_attempt...). Đây là "unenroll",
    không phải xoá tài khoản - sinh viên vẫn đăng nhập được, chỉ không
    còn thấy/truy vấn được tài liệu của lớp này nữa (ACL dựa trên chính
    bảng Enrollment này, xem access_policy.py).
    """
    await _require_course_owner(session, user=user, course_id=course_id)

    result = await session.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == student_user_id,
            Enrollment.role_in_course == "STUDENT",
        )
    )
    enrollment = result.scalar_one_or_none()
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sinh viên này không có trong lớp.",
        )

    await session.delete(enrollment)
    await session.commit()
