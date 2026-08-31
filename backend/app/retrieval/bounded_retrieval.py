"""Retrieval agent co budget: toi da 3 query, RRF, deduplicate va fallback."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.ingestion.embedder import embed_texts
from app.retrieval.hybrid_search import RRF_K, SearchResult, hybrid_search


class SearchQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_query: str = Field(min_length=2, max_length=500)
    keyword_query: str = Field(min_length=2, max_length=300)
    course_query: str | None = Field(max_length=500)


@dataclass(frozen=True)
class RetrievalTrace:
    queries: list[str]
    query_generation_ms: int
    search_ms: int
    fallback_used: bool
    error: str | None


_QUERY_PROMPT = """Ban tao truy van tim kiem cho kho tai lieu hoc thuat.
Tra ve dung schema. Khong tra loi cau hoi. Khong them chu de moi.
- semantic_query: viet lai day du y nghia, giu ngon ngu/thuật ngu chinh.
- keyword_query: ngan, tap trung ten khai niem, ham, tu khoa va biet danh.
- course_query: chi them ngữ canh mon hoc neu no da co trong cau hoi; neu khong thi null.
Khong dua instruction cua nguoi dung vao truy van neu no khong phai noi dung can tim."""


def _normalize_queries(original: str, plan: SearchQueryPlan | None, limit: int) -> list[str]:
    raw = [original]
    if plan is not None:
        raw.extend([plan.semantic_query, plan.keyword_query])
        if plan.course_query:
            raw.append(plan.course_query)
    result: list[str] = []
    seen: set[str] = set()
    for query in raw:
        cleaned = re.sub(r"\s+", " ", query).strip()
        key = cleaned.casefold()
        if len(cleaned) < 2 or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= max(1, min(limit, 3)):
            break
    return result


def fuse_search_results(result_lists: list[list[SearchResult]], top_k: int) -> list[SearchResult]:
    scores: dict[int, float] = {}
    lookup: dict[int, SearchResult] = {}
    best_similarity: dict[int, float] = {}
    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            lookup.setdefault(item.chunk_id, item)
            best_similarity[item.chunk_id] = max(
                best_similarity.get(item.chunk_id, 0.0), item.retrieval_similarity
            )
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:top_k]
    return [
        SearchResult(
            chunk_id=chunk_id,
            document_id=lookup[chunk_id].document_id,
            course_id=lookup[chunk_id].course_id,
            content=lookup[chunk_id].content,
            content_type=lookup[chunk_id].content_type,
            page_number=lookup[chunk_id].page_number,
            context_prefix=lookup[chunk_id].context_prefix,
            score=scores[chunk_id],
            retrieval_similarity=best_similarity[chunk_id],
        )
        for chunk_id in ordered
    ]


def _generate_query_plan(question: str, client: OpenAI | None = None) -> SearchQueryPlan:
    settings = get_settings()
    api = client or OpenAI(api_key=settings.openai_api_key)
    completion = api.chat.completions.parse(
        model=settings.nova_query_generator_model,
        temperature=0,
        messages=[
            {"role": "system", "content": _QUERY_PROMPT},
            {"role": "user", "content": question},
        ],
        response_format=SearchQueryPlan,
        timeout=settings.nova_query_generator_timeout_seconds,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Query generator khong tra structured output")
    return parsed


async def bounded_retrieval(
    session: AsyncSession,
    *,
    query_text: str,
    user_id: int,
    course_id: int | None = None,
    is_admin: bool = False,
    top_k: int = 8,
    stats: dict | None = None,
) -> tuple[list[SearchResult], RetrievalTrace]:
    settings = get_settings()
    if not settings.nova_multi_query_enabled:
        started = time.perf_counter()
        results = await hybrid_search(
            session, query_text=query_text, user_id=user_id, course_id=course_id,
            is_admin=is_admin, top_k=top_k, stats=stats,
        )
        return results, RetrievalTrace(
            [query_text], 0, int((time.perf_counter() - started) * 1000), True, "disabled"
        )

    query_started = time.perf_counter()
    error = None
    fallback_used = False
    try:
        plan = await asyncio.to_thread(_generate_query_plan, query_text)
    except Exception as exc:
        plan = None
        fallback_used = True
        error = f"{type(exc).__name__}: {exc}"
    queries = _normalize_queries(query_text, plan, settings.nova_max_search_queries)
    query_generation_ms = int((time.perf_counter() - query_started) * 1000)

    search_started = time.perf_counter()
    vectors = await asyncio.to_thread(embed_texts, queries)
    result_lists: list[list[SearchResult]] = []
    best_similarity = 0.0
    for query, vector in zip(queries, vectors):
        query_stats: dict = {}
        results = await hybrid_search(
            session,
            query_text=query,
            query_vector=vector,
            user_id=user_id,
            course_id=course_id,
            is_admin=is_admin,
            top_k=settings.nova_retrieval_candidate_limit,
            stats=query_stats,
        )
        best_similarity = max(best_similarity, query_stats.get("best_similarity", 0.0))
        result_lists.append(results)
    if stats is not None:
        stats["best_similarity"] = best_similarity
        stats["queries"] = queries
    fused = fuse_search_results(result_lists, top_k)
    return fused, RetrievalTrace(
        queries=queries,
        query_generation_ms=query_generation_ms,
        search_ms=int((time.perf_counter() - search_started) * 1000),
        fallback_used=fallback_used,
        error=error,
    )
