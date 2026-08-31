import unittest

from app.academic_agent.evidence_planner import EvidencePlan, PlannedClaim, ResponseStyle
from app.academic_agent.response_composer import (
    ComposerCitation,
    build_plan_instruction,
    planned_citation_ids,
    normalize_socratic_answer,
    validate_composer_citation_scope,
    validate_response_contract,
)
from app.retrieval.hybrid_search import SearchResult


def candidate(chunk_id: int) -> SearchResult:
    return SearchResult(chunk_id, 1, 1, "evidence", "text", 1, None, 0.03, 0.7)


def plan() -> EvidencePlan:
    return EvidencePlan(
        intent="explain_concept", answer_mode="grounded", needs_second_retrieval=False,
        follow_up_queries=[],
        claims=[PlannedClaim(claim_id="c1", point="Tuple is immutable", evidence_chunk_ids=[151], confidence="high", source="course_evidence")],
        missing_information=[], must_not_say=[], teaching_strategy="definition_then_example",
        response_style=ResponseStyle(depth="beginner", tone="friendly", length="short", language="vi"),
    )


class ResponseComposerTest(unittest.TestCase):
    def test_prompt_contains_only_planned_claims_and_no_repeat_greeting(self):
        prompt = build_plan_instruction(plan(), is_first_message=False)
        self.assertIn("Tuple is immutable", prompt)
        self.assertIn("Khong chao lai", prompt)
        self.assertIn("SO CLAIM TOI THIEU", prompt)

    def test_citation_scope_drops_unknown_chunk(self):
        citations = [ComposerCitation(chunk_id=151, quote="ok"), ComposerCitation(chunk_id=999, quote="bad")]
        valid = validate_composer_citation_scope(citations, [candidate(151)])
        self.assertEqual(valid, [{"chunk_id": 151, "quote": "ok"}])

    def test_planned_citations_come_from_validated_claim_mapping(self):
        self.assertEqual(planned_citation_ids(plan(), [candidate(151), candidate(999)]), [151])

    def test_socratic_must_end_with_exactly_one_question(self):
        socratic = plan().model_copy(update={"answer_mode": "socratic"})
        validate_response_contract(socratic, "Hay suy nghi. Ban thay sao?")
        with self.assertRaises(ValueError):
            validate_response_contract(socratic, "Ban thay sao? Hay thu tiep.")

    def test_normalizes_fallback_with_multiple_questions(self):
        answer = normalize_socratic_answer("Điều gì xảy ra? Bạn đoán lỗi nào?")
        self.assertEqual(answer.count("?"), 1)
        self.assertTrue(answer.endswith("?"))
        self.assertNotIn("Bạn đoán lỗi nào", answer)


if __name__ == "__main__":
    unittest.main()
