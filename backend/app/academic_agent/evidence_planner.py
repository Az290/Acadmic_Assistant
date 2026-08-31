"""Step 1 cua Agentic RAG: chot claim va evidence truoc khi soan cau tra loi."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import get_settings
from app.retrieval.hybrid_search import SearchResult

AnswerMode = Literal["grounded", "general", "mixed", "insufficient", "refuse", "socratic"]


class PlannedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=40)
    point: str = Field(min_length=1, max_length=1000)
    evidence_chunk_ids: list[int]
    confidence: Literal["low", "medium", "high"]
    source: Literal["course_evidence", "general_knowledge"]


class ResponseStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depth: Literal["beginner", "intermediate", "advanced"]
    tone: Literal["friendly", "neutral", "formal"]
    length: Literal["short", "medium", "long"]
    language: Literal["vi", "en"]


class EvidencePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["explain_concept", "compare", "solve", "summarize", "follow_up", "other"]
    answer_mode: AnswerMode
    needs_second_retrieval: bool
    follow_up_queries: list[str]
    claims: list[PlannedClaim]
    missing_information: list[str]
    must_not_say: list[str]
    teaching_strategy: Literal[
        "direct",
        "definition_then_example",
        "compare_then_example",
        "step_by_step",
        "socratic_questions",
    ]
    response_style: ResponseStyle

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "EvidencePlan":
        if self.answer_mode == "general" and any(claim.evidence_chunk_ids for claim in self.claims):
            raise ValueError("general claim khong duoc mang citation")
        if self.answer_mode in {"grounded", "socratic"}:
            for claim in self.claims:
                if claim.source != "course_evidence" or not claim.evidence_chunk_ids:
                    raise ValueError("grounded/socratic claim phai co course evidence")
        if self.answer_mode == "mixed":
            for claim in self.claims:
                if claim.source == "course_evidence" and not claim.evidence_chunk_ids:
                    raise ValueError("mixed grounded claim phai co evidence")
                if claim.source == "general_knowledge" and claim.evidence_chunk_ids:
                    raise ValueError("mixed general claim khong duoc co citation")
        return self


@dataclass(frozen=True)
class PlannerResult:
    plan: EvidencePlan
    fallback_used: bool
    error: str | None
    latency_ms: int


_SYSTEM_PROMPT = """Ban la Evidence Planner cua tro ly hoc thuat Nova.
Chi lap ke hoach, khong viet cau tra loi cuoi. Moi claim ve tai lieu lop phai tro den
chunk ID that trong danh sach candidates. Khong duoc dua dap an bai/de thi chua
cong bo, thong tin ca nhan, diem hoac quy dinh lop vao general knowledge.
Neu evidence khong du, chon insufficient hoac needs_second_retrieval=true.
Neu cau hoi yeu cau goi mo, chon socratic va teaching_strategy=socratic_questions.
Chi tao claim TOI THIEU can de tra loi DUNG cau hoi, toi da 3 claim, khong lap y.
Voi cau hoi dinh nghia "X la gi", thuong chi can 1 claim dinh nghia; khong tu them
so luong, hieu nang, loi ich, lich su, vi du, ten module hay ung dung neu user khong hoi.
Moi claim phai duoc PHAT BIEU TRUC TIEP trong chunk da gan, khong suy dien tu kien
thuc san co. Khong gan mot claim cho chunk chi vi chunk cung chu de."""


def validate_candidate_scope(plan: EvidencePlan, candidates: list[SearchResult]) -> EvidencePlan:
    allowed = {candidate.chunk_id for candidate in candidates}
    referenced = {
        chunk_id
        for claim in plan.claims
        for chunk_id in claim.evidence_chunk_ids
    }
    invalid = referenced - allowed
    if invalid:
        raise ValueError(f"Planner tham chieu chunk ngoai candidates: {sorted(invalid)}")
    return plan


def apply_question_scope(question: str, plan: EvidencePlan) -> EvidencePlan:
    """Gioi han deterministic cho cau dinh nghia; prompt don thuan chua du on dinh."""
    normalized = question.casefold()
    is_definition = any(marker in normalized for marker in (" là gì", "la gi", "what is "))
    if is_definition and plan.intent == "explain_concept" and len(plan.claims) > 1:
        return plan.model_copy(update={"claims": plan.claims[:1]})
    return plan


def legacy_fallback_plan(*, socratic: bool, has_candidates: bool) -> EvidencePlan:
    mode: AnswerMode
    if not has_candidates:
        mode = "insufficient"
    else:
        mode = "socratic" if socratic else "grounded"
    return EvidencePlan(
        intent="other",
        answer_mode=mode,
        needs_second_retrieval=False,
        follow_up_queries=[],
        claims=[],
        missing_information=[] if has_candidates else ["Khong co evidence phu hop trong tai lieu duoc phep doc."],
        must_not_say=["Khong tu suy dien noi dung khong co trong evidence."],
        teaching_strategy="socratic_questions" if socratic else "direct",
        response_style=ResponseStyle(depth="beginner", tone="friendly", length="short", language="vi"),
    )


def plan_evidence(
    *,
    question: str,
    search_query: str,
    candidates: list[SearchResult],
    history: list[dict] | None = None,
    effective_role: str = "STUDENT",
    socratic: bool = False,
    client: OpenAI | None = None,
    enabled: bool | None = None,
) -> PlannerResult:
    """Tao plan co schema; moi loi deu fallback ve legacy RAG, khong lam sap chat."""
    settings = get_settings()
    fallback = legacy_fallback_plan(socratic=socratic, has_candidates=bool(candidates))
    if enabled is False or not settings.nova_evidence_planner_enabled:
        return PlannerResult(fallback, True, "disabled", 0)

    started = time.perf_counter()
    candidate_text = "\n\n".join(
        f"chunk_id={item.chunk_id}; document_id={item.document_id}; page={item.page_number}; "
        f"score={item.score:.6f}\n{item.content[:2200]}"
        for item in candidates
    ) or "(khong co candidate)"
    history_text = "\n".join(
        f"{item.get('role', 'unknown')}: {str(item.get('content', ''))[:800]}"
        for item in (history or [])[-10:]
    ) or "(khong co lich su)"
    user_prompt = (
        f"Role: {effective_role}\nSocratic requested: {socratic}\n"
        f"Cau hoi goc: {question}\nSearch query: {search_query}\n"
        f"Lich su gan day:\n{history_text}\n\nCandidates:\n{candidate_text}"
    )

    try:
        api = client or OpenAI(api_key=settings.openai_api_key)
        completion = api.chat.completions.parse(
            model=settings.nova_evidence_planner_model,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=EvidencePlan,
            timeout=settings.nova_evidence_planner_timeout_seconds,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Planner khong tra ve structured output")
        plan = validate_candidate_scope(apply_question_scope(question, parsed), candidates)
        return PlannerResult(plan, False, None, int((time.perf_counter() - started) * 1000))
    except Exception as exc:
        return PlannerResult(
            fallback,
            True,
            f"{type(exc).__name__}: {exc}",
            int((time.perf_counter() - started) * 1000),
        )
