"""LLM reranker co schema, chi duoc sap xep candidate da qua ACL."""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.retrieval.hybrid_search import SearchResult


class RankedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: int
    relevance: int = Field(ge=0, le=3)
    reason: str = Field(min_length=1, max_length=240)


class RerankPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rankings: list[RankedChunk]


@dataclass(frozen=True)
class RerankTrace:
    latency_ms: int
    fallback_used: bool
    error: str | None


_PROMPT = """Ban xep hang cac doan tai lieu cho mot cau hoi hoc thuat.
Chi danh gia candidate da cho, khong them chunk ID. Cham relevance:
3=tra loi truc tiep, 2=bang chung bo tro quan trong, 1=co lien quan nhe, 0=khong lien quan.
Tra ve moi chunk dung mot lan, xep relevance giam dan; neu bang diem thi uu tien
doan tra loi cu the hon. Khong tra loi cau hoi."""


def apply_rerank_plan(
    candidates: list[SearchResult], plan: RerankPlan, top_k: int
) -> list[SearchResult]:
    lookup = {item.chunk_id: item for item in candidates}
    seen: set[int] = set()
    ordered: list[SearchResult] = []
    for ranking in sorted(plan.rankings, key=lambda item: -item.relevance):
        if ranking.chunk_id in seen or ranking.chunk_id not in lookup:
            continue
        seen.add(ranking.chunk_id)
        if ranking.relevance > 0:
            ordered.append(lookup[ranking.chunk_id])
    # Schema hop le nhung model bo sot candidate: noi lai theo thu tu legacy de
    # reranker khong the lam mat toan bo evidence.
    ordered.extend(item for item in candidates if item.chunk_id not in seen)
    return ordered[:top_k]


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFD", text.casefold())
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return {
        token
        for token in re.findall(r"[a-z0-9_+]{2,}", without_marks)
        if token not in {"la", "gi", "va", "co", "cho", "trong", "the", "nao", "mot"}
    }


def local_rerank_results(
    question: str, candidates: list[SearchResult], top_k: int = 8
) -> list[SearchResult]:
    """Rerank noi bo, khong gui noi dung tai lieu ra dich vu ben ngoai."""
    query_tokens = _tokens(question)
    if not query_tokens:
        return candidates[:top_k]

    def score(index_and_item: tuple[int, SearchResult]) -> tuple[float, float, int]:
        index, item = index_and_item
        document_tokens = _tokens(f"{item.context_prefix or ''} {item.content}")
        overlap = len(query_tokens & document_tokens) / len(query_tokens)
        # Lexical la tin hieu bo sung, legacy RRF van giu vai tro tie-break de
        # khong pha thu tu semantic khi overlap bang nhau.
        return overlap, item.score, -index

    ranked = sorted(enumerate(candidates), key=score, reverse=True)
    return [item for _, item in ranked[:top_k]]


def _call_reranker(
    question: str, candidates: list[SearchResult], client: OpenAI | None = None
) -> RerankPlan:
    settings = get_settings()
    api = client or OpenAI(api_key=settings.openai_api_key)
    candidate_text = "\n\n".join(
        f"chunk_id={item.chunk_id}; page={item.page_number}; heading={item.context_prefix}\n{item.content[:1800]}"
        for item in candidates
    )
    completion = api.chat.completions.parse(
        model=settings.nova_reranker_model,
        temperature=0,
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": f"Cau hoi: {question}\n\nCandidates:\n{candidate_text}"},
        ],
        response_format=RerankPlan,
        timeout=settings.nova_reranker_timeout_seconds,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Reranker khong tra structured output")
    return parsed


async def rerank_results(
    *, question: str, candidates: list[SearchResult], top_k: int = 8
) -> tuple[list[SearchResult], RerankTrace]:
    settings = get_settings()
    if not settings.nova_reranker_enabled or not candidates:
        return candidates[:top_k], RerankTrace(0, True, "disabled" if candidates else None)
    started = time.perf_counter()
    try:
        plan = await asyncio.to_thread(_call_reranker, question, candidates)
        ranked = apply_rerank_plan(candidates, plan, top_k)
        return ranked, RerankTrace(int((time.perf_counter() - started) * 1000), False, None)
    except Exception as exc:
        return candidates[:top_k], RerankTrace(
            int((time.perf_counter() - started) * 1000), True, f"{type(exc).__name__}: {exc}"
        )
