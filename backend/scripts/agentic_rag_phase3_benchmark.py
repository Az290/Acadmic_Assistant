"""Benchmark retrieval Phase 3: Recall@K, MRR, false hit va latency."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.retrieval.bounded_retrieval import bounded_retrieval  # noqa: E402
from app.retrieval.hybrid_search import hybrid_search  # noqa: E402
from app.retrieval.reranker import local_rerank_results, rerank_results  # noqa: E402

DATASET = Path(__file__).parent / "benchmarks" / "phase3_retrieval_cases.json"
RESULTS_DIR = Path(__file__).parent / "benchmarks" / "results"


def metrics(expected: list[int], actual: list[int]) -> tuple[float | None, float | None]:
    if not expected:
        return None, None
    recall = sum(chunk_id in actual for chunk_id in expected) / len(expected)
    relevant_ranks = [actual.index(chunk_id) + 1 for chunk_id in expected if chunk_id in actual]
    mrr = 1 / min(relevant_ranks) if relevant_ranks else 0.0
    return recall, mrr


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--strategy", choices=["legacy", "bounded", "local_rerank", "rerank"], default="legacy")
    args = parser.parse_args()
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = []
    async with AsyncSessionLocal() as session:
        for case in dataset["cases"]:
            started = time.perf_counter()
            stats = {}
            if args.strategy == "bounded":
                settings = get_settings()
                old_enabled = settings.nova_multi_query_enabled
                settings.nova_multi_query_enabled = True
                try:
                    results, trace = await bounded_retrieval(
                        session,
                        query_text=case["query"],
                        user_id=dataset["user_id"],
                        course_id=dataset["course_id"],
                        stats=stats,
                    )
                finally:
                    settings.nova_multi_query_enabled = old_enabled
                rerank_trace = None
            else:
                results = await hybrid_search(
                    session,
                    query_text=case["query"],
                    user_id=dataset["user_id"],
                    course_id=dataset["course_id"],
                    stats=stats,
                    top_k=20 if args.strategy in {"rerank", "local_rerank"} else 8,
                )
                trace = None
                rerank_trace = None
                if args.strategy == "rerank":
                    settings = get_settings()
                    old_enabled = settings.nova_reranker_enabled
                    settings.nova_reranker_enabled = True
                    try:
                        results, rerank_trace = await rerank_results(
                            question=case["query"], candidates=results, top_k=8
                        )
                    finally:
                        settings.nova_reranker_enabled = old_enabled
                elif args.strategy == "local_rerank":
                    results = local_rerank_results(case["query"], results, top_k=8)
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            actual = [item.chunk_id for item in results]
            recall, mrr = metrics(case["expected_chunk_ids"], actual)
            rows.append(
                {
                    **case,
                    "actual_chunk_ids": actual,
                    "recall_at_8": recall,
                    "mrr": mrr,
                    "false_hit": not case["expected_chunk_ids"] and bool(actual),
                    "best_similarity": stats.get("best_similarity"),
                    "queries": trace.queries if trace else [case["query"]],
                    "query_generation_ms": trace.query_generation_ms if trace else 0,
                    "search_ms": trace.search_ms if trace else latency_ms,
                    "fallback_used": trace.fallback_used if trace else False,
                    "rerank_ms": rerank_trace.latency_ms if rerank_trace else 0,
                    "rerank_fallback": rerank_trace.fallback_used if rerank_trace else False,
                    "latency_ms": latency_ms,
                }
            )

    positive = [row for row in rows if row["recall_at_8"] is not None]
    negative = [row for row in rows if row["recall_at_8"] is None]
    summary = {
        "cases": len(rows),
        "mean_recall_at_8": round(statistics.mean(row["recall_at_8"] for row in positive), 3),
        "mean_mrr": round(statistics.mean(row["mrr"] for row in positive), 3),
        "complete_recall_rate": round(sum(row["recall_at_8"] == 1 for row in positive) / len(positive), 3),
        "false_hit_rate": round(sum(row["false_hit"] for row in negative) / len(negative), 3),
        "median_latency_ms": round(statistics.median(row["latency_ms"] for row in rows), 1),
        "p95_latency_ms": round(sorted(row["latency_ms"] for row in rows)[max(0, int(len(rows) * 0.95) - 1)], 1),
    }
    report = {
        "label": args.label,
        "strategy": args.strategy,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "cases": rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / f"phase3_{args.label}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
