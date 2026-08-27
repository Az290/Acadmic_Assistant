from datetime import datetime, timezone
from types import SimpleNamespace

from app.academic_agent.prompts import build_learning_progress_block


def test_learning_progress_block_contains_verified_assignment_facts() -> None:
    context = SimpleNamespace(
        assignments=[
            SimpleNamespace(
                title="Ôn tập Python",
                question_count=10,
                submitted=False,
                overdue=True,
                due_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                score=None,
                total=None,
            ),
            SimpleNamespace(
                title="Danh sách cơ bản",
                question_count=4,
                submitted=True,
                overdue=False,
                due_at=None,
                score=3,
                total=4,
            ),
        ],
        recent_assignment_answers=[
            SimpleNamespace(
                assignment_title="Danh sách cơ bản",
                concept_name="List trong Python",
                question="Chỉ số đầu tiên là bao nhiêu?",
                your_answer="1",
                correct_answer="0",
                is_correct=False,
            )
        ],
    )

    block = build_learning_progress_block(context)

    assert "1 đã nộp, 1 chưa nộp" in block
    assert "QUÁ HẠN" in block
    assert "điểm 3/4" in block
    assert "[SAI]" in block
    assert "đã chọn: 1" in block
    assert "đáp án đúng: 0" in block


def test_learning_progress_block_is_empty_without_assignments() -> None:
    context = SimpleNamespace(assignments=[], recent_assignment_answers=[])
    assert build_learning_progress_block(context) == ""
