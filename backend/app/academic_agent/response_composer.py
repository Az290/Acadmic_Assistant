"""Step 2 cua Agentic RAG: viet cau tra loi tu EvidencePlan da kiem tra."""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.academic_agent.evidence_planner import EvidencePlan
from app.config import get_settings
from app.retrieval.hybrid_search import SearchResult


class ComposerCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: int
    quote: str = Field(min_length=1, max_length=300)


class ComposerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=10000)
    citations: list[ComposerCitation]


@dataclass(frozen=True)
class ComposerResult:
    answer: str
    citations: list[dict]
    fallback_used: bool
    error: str | None


def build_plan_instruction(plan: EvidencePlan | None, *, is_first_message: bool) -> str:
    if plan is None:
        return ""
    claims = "\n".join(
        f"- {claim.claim_id}: {claim.point}; source={claim.source}; chunks={claim.evidence_chunk_ids}"
        for claim in plan.claims
    ) or "- Khong co claim factual nao duoc phep."
    missing = "; ".join(plan.missing_information) or "khong"
    greeting = (
        "Co the chao mot cau ngan vi day la luot dau." if is_first_message
        else "Khong chao lai; vao thang noi dung."
    )
    return f"""

RESPONSE COMPOSER CONTRACT:
- Answer mode: {plan.answer_mode}
- Teaching strategy: {plan.teaching_strategy}
- Style: depth={plan.response_style.depth}, tone={plan.response_style.tone}, length={plan.response_style.length}, language={plan.response_style.language}
- {greeting}
- Missing information: {missing}
- Chi duoc dien dat cac factual claims sau:
{claims}
- Dung SO CLAIM TOI THIEU de tra loi dung dieu user hoi; khong can dung het claims.
- Khong lap lai cung mot y bang hai cach dien dat khac nhau.
- Khong them con so, ten rieng, vi du factual hoac ket luan moi ngoai claims/evidence.
- Khong lap cau "dua tren tai lieu" neu citation da the hien nguon.
- Neu insufficient: noi ro thieu thong tin, khong lap day bang kien thuc chung.
- Neu socratic: khong doc dap an truc tiep; ket thuc bang dung mot cau hoi goi mo.
"""


def validate_composer_citation_scope(
    citations: list[ComposerCitation], candidates: list[SearchResult]
) -> list[dict]:
    allowed = {item.chunk_id for item in candidates}
    return [citation.model_dump() for citation in citations if citation.chunk_id in allowed]


def validate_response_contract(plan: EvidencePlan | None, answer: str) -> None:
    if plan is not None and plan.answer_mode == "socratic":
        question_count = answer.count("?")
        if question_count != 1 or not answer.rstrip().endswith("?"):
            raise ValueError(
                "Socratic response phai ket thuc bang dung mot cau hoi "
                f"(question_count={question_count})"
            )


def normalize_socratic_answer(answer: str) -> str:
    """Bao dam output cuoi van dung contract ke ca khi Composer roi ve fallback."""
    stripped = answer.strip()
    first_question_end = stripped.find("?")
    if first_question_end >= 0:
        # Cat ngay sau cau hoi goi mo dau tien: loai cau hoi don va cac claim
        # giai thich them ma model co the chen sau do.
        return stripped[: first_question_end + 1]
    statement = stripped.rstrip(". ")
    return f"{statement}. Bạn sẽ trả lời gợi ý này như thế nào?"


def planned_citation_ids(
    plan: EvidencePlan | None, candidates: list[SearchResult]
) -> list[int]:
    """Nguon citation chinh la claim-evidence mapping da duoc planner validate."""
    if plan is None or plan.answer_mode in {"general", "insufficient", "refuse"}:
        return []
    allowed = {item.chunk_id for item in candidates}
    ordered: list[int] = []
    for claim in plan.claims:
        for chunk_id in claim.evidence_chunk_ids:
            if chunk_id in allowed and chunk_id not in ordered:
                ordered.append(chunk_id)
    return ordered


def compose_grounded_response(
    *,
    messages: list[dict],
    model: str,
    temperature: float | None,
    plan: EvidencePlan | None,
    candidates: list[SearchResult],
    is_first_message: bool,
    client: OpenAI | None = None,
    enabled: bool | None = None,
) -> ComposerResult:
    settings = get_settings()
    if enabled is False or not settings.nova_response_composer_enabled:
        return ComposerResult("", [], True, "disabled")

    composer_messages = list(messages)
    instruction = build_plan_instruction(plan, is_first_message=is_first_message)
    if instruction:
        composer_messages.insert(1, {"role": "system", "content": instruction})
    try:
        api = client or OpenAI(api_key=settings.openai_api_key)
        kwargs = {
            "model": model,
            "messages": composer_messages,
            "response_format": ComposerResponse,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        completion = api.chat.completions.parse(**kwargs)
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Composer khong tra structured output")
        answer = parsed.answer
        if plan is not None and plan.answer_mode == "socratic":
            answer = normalize_socratic_answer(answer)
        validate_response_contract(plan, answer)
        return ComposerResult(
            answer,
            validate_composer_citation_scope(parsed.citations, candidates),
            False,
            None,
        )
    except Exception as exc:
        return ComposerResult("", [], True, f"{type(exc).__name__}: {exc}")
