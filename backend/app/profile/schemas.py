from pydantic import BaseModel


class ProfileStats(BaseModel):
    """
    Thống kê sử dụng của CHÍNH người dùng đang đăng nhập - không phải
    Dashboard giảng viên (app/instructor/), không có số liệu người khác.
    """

    total_questions: int
    questions_this_week: int
    quizzes_taken: int
    # None nếu chưa có lượt quan sát nào (StudentMastery rỗng) - tránh
    # hiện "0%" gây hiểu nhầm "đã học nhưng kém", trong khi thực ra là
    # "chưa học gì cả".
    avg_mastery: float | None
