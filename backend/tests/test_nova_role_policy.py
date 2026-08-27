import asyncio
from types import SimpleNamespace

from app.academic_agent.prompts import (
    DEADLINE_ALERT_HEADING,
    build_deadline_alert_block,
    build_system_prompt,
)
from app.academic_agent.role_policy import resolve_role_context
from app.academic_agent.tools import get_tools_for_role
from app.learning.student_context import load_student_context


def test_deadline_alert_is_built_once_with_stable_heading() -> None:
    context = SimpleNamespace(
        assignments=[
            SimpleNamespace(
                title="Bài đệ quy",
                submitted=False,
                overdue=False,
                due_soon=True,
                due_at=SimpleNamespace(isoformat=lambda: "2026-08-29T12:00:00+00:00"),
            )
        ]
    )

    first = build_deadline_alert_block(context, already_alerted=False)
    repeated = build_deadline_alert_block(context, already_alerted=True)

    assert DEADLINE_ALERT_HEADING in first
    assert "trong 48 giờ" in first
    assert repeated == ""


def test_instructor_prompt_uses_instructor_policy_without_student_profile() -> None:
    prompt = build_system_prompt(
        "CHITCHAT",
        "",
        effective_role="INSTRUCTOR",
        active_course_id=10,
    )

    assert "VAI TRÒ HIỆU LỰC: GIẢNG VIÊN" in prompt
    assert "Không đọc hoặc suy luận từ nội dung chat riêng" in prompt
    assert "HỒ SƠ HỌC TẬP ĐÃ XÁC MINH" not in prompt


def test_tools_are_filtered_by_effective_role() -> None:
    student_names = {tool["function"]["name"] for tool in get_tools_for_role("STUDENT")}
    instructor_names = {tool["function"]["name"] for tool in get_tools_for_role("INSTRUCTOR")}

    assert "get_my_assignments" in student_names
    assert "get_student_assignment_details" not in student_names
    assert "get_student_assignment_details" in instructor_names
    assert "draft_assignment_reminder" in instructor_names


def test_student_context_without_confirmed_course_does_not_query_database() -> None:
    class FailingSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("Không được query khi chưa xác định lớp")

    context = asyncio.run(
        load_student_context(
            FailingSession(),
            user_id=1,
            course_id=None,
            user_role="STUDENT",
        )
    )
    assert context.assignments == []
    assert context.concepts == []


def test_role_in_course_overrides_global_instructor_role() -> None:
    class ScalarResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class SequenceSession:
        def __init__(self):
            self.values = iter([999, "STUDENT"])

        async def execute(self, *_args, **_kwargs):
            return ScalarResult(next(self.values))

    role = asyncio.run(
        resolve_role_context(
            SequenceSession(),
            user_id=7,
            global_role="INSTRUCTOR",
            course_id=42,
        )
    )

    assert role.effective_role == "STUDENT"
    assert role.has_course_access is True
