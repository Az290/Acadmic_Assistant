import unittest

from pydantic import ValidationError

from app.academic_agent.evidence_planner import (
    EvidencePlan,
    PlannedClaim,
    ResponseStyle,
    apply_question_scope,
    legacy_fallback_plan,
    validate_candidate_scope,
)
from app.retrieval.hybrid_search import SearchResult


def candidate(chunk_id: int) -> SearchResult:
    return SearchResult(chunk_id, 1, 1, "Noi dung", "text", 1, None, 0.03, 0.7)


def style() -> ResponseStyle:
    return ResponseStyle(depth="beginner", tone="friendly", length="short", language="vi")


class EvidencePlannerContractTest(unittest.TestCase):
    def test_grounded_claim_requires_evidence(self):
        with self.assertRaises(ValidationError):
            EvidencePlan(
                intent="explain_concept", answer_mode="grounded", needs_second_retrieval=False,
                follow_up_queries=[], claims=[PlannedClaim(claim_id="c1", point="x", evidence_chunk_ids=[], confidence="high", source="course_evidence")],
                missing_information=[], must_not_say=[], teaching_strategy="direct", response_style=style(),
            )

    def test_general_claim_cannot_have_citation(self):
        with self.assertRaises(ValidationError):
            EvidencePlan(
                intent="other", answer_mode="general", needs_second_retrieval=False,
                follow_up_queries=[], claims=[PlannedClaim(claim_id="c1", point="x", evidence_chunk_ids=[1], confidence="high", source="general_knowledge")],
                missing_information=[], must_not_say=[], teaching_strategy="direct", response_style=style(),
            )

    def test_rejects_chunk_outside_candidates(self):
        plan = EvidencePlan(
            intent="explain_concept", answer_mode="grounded", needs_second_retrieval=False,
            follow_up_queries=[], claims=[PlannedClaim(claim_id="c1", point="x", evidence_chunk_ids=[99], confidence="high", source="course_evidence")],
            missing_information=[], must_not_say=[], teaching_strategy="direct", response_style=style(),
        )
        with self.assertRaises(ValueError):
            validate_candidate_scope(plan, [candidate(1)])

    def test_fallback_is_bounded_and_deterministic(self):
        plan = legacy_fallback_plan(socratic=False, has_candidates=True)
        self.assertEqual(plan.answer_mode, "grounded")
        self.assertFalse(plan.needs_second_retrieval)
        self.assertEqual(plan.claims, [])

    def test_definition_question_keeps_only_core_claim(self):
        base = EvidencePlan(
            intent="explain_concept", answer_mode="grounded", needs_second_retrieval=False,
            follow_up_queries=[], claims=[
                PlannedClaim(claim_id="c1", point="definition", evidence_chunk_ids=[1], confidence="high", source="course_evidence"),
                PlannedClaim(claim_id="c2", point="extra", evidence_chunk_ids=[1], confidence="high", source="course_evidence"),
            ], missing_information=[], must_not_say=[], teaching_strategy="direct", response_style=style(),
        )
        scoped = apply_question_scope("Python là gì?", base)
        self.assertEqual([claim.claim_id for claim in scoped.claims], ["c1"])


if __name__ == "__main__":
    unittest.main()
    apply_question_scope,
