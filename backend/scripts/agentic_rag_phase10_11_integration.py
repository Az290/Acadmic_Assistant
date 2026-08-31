"""Real API/DB integration for Phase 10 operations and Phase 11 instructor scope."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.academic_agent.instructor_context import load_instructor_context  # noqa: E402
from app.academic_agent.tool_executor import (  # noqa: E402
    _tool_get_my_courses_overview,
    _tool_get_teaching_recommendations,
)
from app.academic_agent.system_kb_service import SystemKBQuerier  # noqa: E402
from app.db.models import AppUser  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402

BASE = "http://127.0.0.1:8001"
OUT = Path(__file__).parent / "benchmarks" / "results" / "phase10_11_integration.json"


def login(email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE, timeout=30)
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    for name in ("access_token", "refresh_token"):
        if name in response.cookies:
            client.cookies.set(name, response.cookies[name])
    return client


async def check_instructor_scope(course_id: int):
    async with AsyncSessionLocal() as session:
        owner = (await session.execute(select(AppUser).where(
            AppUser.email == "gv.nguyenvana@test.edu.vn"
        ))).scalar_one()
        other = (await session.execute(select(AppUser).where(
            AppUser.email == "gv.giangvien2@test.edu.vn"
        ))).scalar_one()
        context = await load_instructor_context(session, course_id=course_id, effective_role="INSTRUCTOR")
        owner_result = await _tool_get_teaching_recommendations(session, {"course_id": course_id}, owner)
        courses_overview = await _tool_get_my_courses_overview(session, {}, owner)
        other_result = await _tool_get_teaching_recommendations(session, {"course_id": course_id}, other)
        kb = SystemKBQuerier(session)
        instructor_kb = await kb.query("upload tai lieu pdf", owner.id, "INSTRUCTOR")
        student_kb = await kb.query("upload tai lieu pdf", owner.id, "STUDENT")
        return context, owner_result, other_result, courses_overview, instructor_kb, student_kb


def main() -> int:
    admin = login("admin@test.edu.vn", "Admin@123")
    student = login("sv.sinhvien1@test.edu.vn", "Student@123")
    instructor = login("gv.nguyenvana@test.edu.vn", "Instructor@123")
    courses = instructor.get("/v1/courses/me").json()
    course = next(item for item in courses if item.get("owner_id"))
    status = admin.get("/v1/operations/status")
    preview = admin.get("/v1/operations/retention/preview")
    forbidden = student.get("/v1/operations/status")
    context, owner_result, other_result, courses_overview, instructor_kb, student_kb = asyncio.run(check_instructor_scope(course["id"]))
    checks = {
        "operations_admin_only": status.status_code == 200 and forbidden.status_code == 403,
        "operations_has_rollout_gate": status.status_code == 200 and "rollback_recommended" in status.json(),
        "retention_preview_non_destructive": preview.status_code == 200 and "events" in preview.json(),
        "instructor_context_course_scoped": context.course_id == course["id"],
        "instructor_context_is_aggregate": context.total_students >= context.students_with_data,
        "owner_gets_teaching_recommendations": owner_result.success and "evidence" in owner_result.data,
        "owner_courses_are_loaded": courses_overview.success and courses_overview.data["course_count"] > 0,
        "course_overview_has_students": courses_overview.success and all(
            "student_count" in item and "students_needing_support" in item
            for item in courses_overview.data["courses"]
        ),
        "cross_course_owner_blocked": not other_result.success,
        "no_private_chat_in_tool_result": "conversation" not in json.dumps(owner_result.data).lower(),
        "instructor_kb_scoped": instructor_kb.category == "INSTRUCTOR_DOCUMENT_SUPPORT",
        "student_does_not_get_instructor_kb": student_kb.category != "INSTRUCTOR_DOCUMENT_SUPPORT",
    }
    report = {"summary": {"cases": len(checks), "passed": sum(checks.values()),
                           "pass_rate": sum(checks.values()) / len(checks)}, "cases": checks}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
