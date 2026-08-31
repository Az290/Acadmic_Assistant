import asyncio
import unittest

from app.academic_agent.instructor_context import ConceptGap, InstructorContext, build_instructor_context_block
from app.academic_agent.prompts import build_system_prompt
from app.academic_agent.role_policy import resolve_role_context
from app.academic_agent.tools import get_tools_for_role
from app.router_agent.classifier import classify


class Phase11InstructorAssistantTests(unittest.TestCase):
    def test_system_knowledge_is_role_specific(self):
        instructor = build_system_prompt("SYSTEM_QUESTION", "", effective_role="INSTRUCTOR", active_course_id=1)
        student = build_system_prompt("SYSTEM_QUESTION", "", effective_role="STUDENT", active_course_id=1)
        self.assertIn("dành riêng cho GIẢNG VIÊN", instructor)
        self.assertIn("không tự gửi email/Zalo/notification", instructor)
        self.assertNotIn("dành riêng cho GIẢNG VIÊN", student)

    def test_aggregate_context_has_evidence_but_no_identity_or_chat(self):
        block = build_instructor_context_block(InstructorContext(
            course_id=3, total_students=20, students_with_data=12, weak_student_count=4,
            strong_student_count=3, average_mastery=0.61,
            concept_gaps=[ConceptGap("Đệ quy", 30, 0.33)], assignment_count=2, submission_count=18,
        ))
        self.assertIn("33%, 30 luot", block)
        self.assertIn("Khong suy dien tu chat rieng", block)
        self.assertNotIn("Nguyen Van A", block)

    def test_instructor_only_teaching_tool(self):
        instructor = {x["function"]["name"] for x in get_tools_for_role("INSTRUCTOR")}
        student = {x["function"]["name"] for x in get_tools_for_role("STUDENT")}
        self.assertIn("get_teaching_recommendations", instructor)
        self.assertIn("get_my_courses_overview", instructor)
        self.assertNotIn("get_teaching_recommendations", student)
        self.assertNotIn("get_my_courses_overview", student)

    def test_course_role_overrides_global_instructor(self):
        class Result:
            def __init__(self, value): self.value = value
            def scalar_one_or_none(self): return self.value
        class Session:
            def __init__(self): self.values = iter([999, "STUDENT"])
            async def execute(self, *_args, **_kwargs): return Result(next(self.values))
        role = asyncio.run(resolve_role_context(Session(), user_id=7, global_role="INSTRUCTOR", course_id=42))
        self.assertEqual(role.effective_role, "STUDENT")

    def test_my_courses_question_routes_to_action_without_llm(self):
        route = classify("Tôi đang có bao nhiêu lớp và mỗi lớp bao nhiêu sinh viên?")
        self.assertEqual(route.category, "ACTION_REQUEST")
        self.assertEqual(route.classified_by, "rules")


if __name__ == "__main__":
    unittest.main()
