"""Benchmark contract, fallback va chat luong co ban cua Evidence Planner."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.academic_agent.evidence_planner import plan_evidence  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.retrieval.hybrid_search import SearchResult  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "benchmarks" / "results"


def chunk(chunk_id: int, content: str) -> SearchResult:
    return SearchResult(chunk_id, 7, 1, content, "text", 10, "Python", 0.03, 0.72)


CASES = [
    {
        "id": "grounded-definition",
        "question": "Python la gi?",
        "socratic": False,
        "candidates": [chunk(101, "Python is a high-level, interpreted programming language.")],
        "allowed_modes": {"grounded"},
    },
    {
        "id": "socratic-with-evidence",
        "question": "Dung cho dap an ngay, hay giup toi tu hieu list comprehension",
        "socratic": True,
        "candidates": [chunk(102, "A list comprehension creates a list from an iterable using an expression.")],
        "allowed_modes": {"socratic"},
    },
    {
        "id": "insufficient",
        "question": "Tai lieu lop noi gi ve quantum networking?",
        "socratic": False,
        "candidates": [],
        "allowed_modes": {"insufficient"},
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    original_enabled = settings.nova_evidence_planner_enabled
    settings.nova_evidence_planner_enabled = args.live
    rows = []
    try:
        for case in CASES:
            result = plan_evidence(
                question=case["question"],
                search_query=case["question"],
                candidates=case["candidates"],
                socratic=case["socratic"],
            )
            candidate_ids = {item.chunk_id for item in case["candidates"]}
            cited_ids = {
                cid for claim in result.plan.claims for cid in claim.evidence_chunk_ids
            }
            rows.append(
                {
                    "id": case["id"],
                    "answer_mode": result.plan.answer_mode,
                    "mode_match": result.plan.answer_mode in case["allowed_modes"],
                    "scope_valid": cited_ids <= candidate_ids,
                    "claims": len(result.plan.claims),
                    "fallback_used": result.fallback_used,
                    "error": result.error,
                    "latency_ms": result.latency_ms,
                }
            )
    finally:
        settings.nova_evidence_planner_enabled = original_enabled

    summary = {
        "cases": len(rows),
        "schema_success_rate": round(sum(row["error"] is None for row in rows) / len(rows), 3),
        "mode_accuracy": round(sum(row["mode_match"] for row in rows) / len(rows), 3),
        "scope_validation_rate": round(sum(row["scope_valid"] for row in rows) / len(rows), 3),
        "fallback_rate": round(sum(row["fallback_used"] for row in rows) / len(rows), 3),
        "median_latency_ms": statistics.median(row["latency_ms"] for row in rows),
    }
    report = {
        "label": args.label,
        "live": args.live,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "cases": rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / f"phase2_{args.label}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report: {output}")
    passed = all(row["mode_match"] and row["scope_valid"] for row in rows)
    if args.live:
        passed = passed and all(not row["fallback_used"] and row["error"] is None for row in rows)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
