import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.academic_agent.instructor_context import ConceptGap, InstructorContext, build_instructor_context_block  # noqa: E402
from app.academic_agent.prompts import build_system_prompt  # noqa: E402
from app.academic_agent.role_policy import resolve_role_context  # noqa: E402
from app.academic_agent.tools import get_tools_for_role  # noqa: E402


class Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class Session:
    def __init__(self, values): self.values = iter(values)
    async def execute(self, *_args, **_kwargs): return Result(next(self.values))


def main() -> int:
    instructor_prompt = build_system_prompt("SYSTEM_QUESTION", "", effective_role="INSTRUCTOR", active_course_id=1)
    student_prompt = build_system_prompt("SYSTEM_QUESTION", "", effective_role="STUDENT", active_course_id=1)
    aggregate = build_instructor_context_block(InstructorContext(
        course_id=1, total_students=10, students_with_data=8, weak_student_count=2,
        strong_student_count=3, average_mastery=.67, concept_gaps=[ConceptGap("Recursion", 20, .35)]
    ))
    course_student = asyncio.run(resolve_role_context(Session([99, "STUDENT"]), user_id=7,
                                                              global_role="INSTRUCTOR", course_id=1))
    instructor_tools = {x["function"]["name"] for x in get_tools_for_role("INSTRUCTOR")}
    student_tools = {x["function"]["name"] for x in get_tools_for_role("STUDENT")}
    checks = {
        "instructor_kb_selected": "dành riêng cho GIẢNG VIÊN" in instructor_prompt,
        "student_kb_separate": "dành riêng cho GIẢNG VIÊN" not in student_prompt,
        "instructor_not_told_wait_for_other_teacher": "phải chờ giảng viên duyệt" not in instructor_prompt,
        "aggregate_has_weak_strong": "Nhom can ho tro" in aggregate and "nhom dang lam tot" in aggregate,
        "aggregate_has_concept_evidence": "Recursion (35%, 20 luot)" in aggregate,
        "aggregate_has_no_private_chat": "Conversation" not in aggregate and "Message" not in aggregate,
        "global_instructor_can_be_course_student": course_student.effective_role == "STUDENT",
        "teaching_tool_instructor_only": "get_teaching_recommendations" in instructor_tools and "get_teaching_recommendations" not in student_tools,
        "student_cannot_detail_other_student": "get_student_assignment_details" not in student_tools,
        "individual_detail_tool_available_to_owner": "get_student_assignment_details" in instructor_tools,
    }
    print(json.dumps({"phase": 11, "passed": sum(checks.values()), "total": len(checks), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
