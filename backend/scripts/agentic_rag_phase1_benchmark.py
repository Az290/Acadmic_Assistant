"""Benchmark Phase 1: routing va quyet dinh co retrieval hay khong.

Chay tu thu muc backend:
    python scripts/agentic_rag_phase1_benchmark.py --label baseline

Script co hai phan:
- Kiem tra hop dong UI: tab Hoi dap phai de Router tu quyet dinh; chi tab Gia su
  moi duoc ep SOCRATIC_REQUEST.
- Goi classifier that de do category, retrieval decision va latency.

Ket qua JSON duoc luu trong scripts/benchmarks/results de so sanh qua tung phase.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
DATASET_PATH = Path(__file__).parent / "benchmarks" / "phase1_routing_cases.json"
RESULTS_DIR = Path(__file__).parent / "benchmarks" / "results"
CHAT_BUBBLE_PATH = ROOT_DIR / "frontend" / "components" / "ChatBubble.tsx"

sys.path.insert(0, str(BACKEND_DIR))


def check_frontend_contract() -> dict:
    source = CHAT_BUBBLE_PATH.read_text(encoding="utf-8")
    expected_pattern = re.compile(
        r'activeTab\s*===\s*"SOCRATIC_REQUEST"\s*\?\s*"SOCRATIC_REQUEST"\s*:\s*undefined'
    )
    legacy = "isInstructorContext ? undefined : activeTab"
    passed = bool(expected_pattern.search(source)) and legacy not in source
    return {
        "passed": passed,
        "expected": "Hoi dap=auto route; Gia su=SOCRATIC_REQUEST",
        "observed": "correct" if passed else "Hoi dap dang bi ep RAG_QUESTION",
    }


def run_classifier_cases() -> list[dict]:
    from app.router_agent.classifier import classify

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    results = []
    for case in dataset["cases"]:
        started = time.perf_counter()
        try:
            route = classify(case["message"])
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            results.append(
                {
                    **case,
                    "actual_category": route.category,
                    "actual_retrieval": route.needs_retrieval,
                    "category_match": route.category == case["expected_category"],
                    "retrieval_match": route.needs_retrieval == case["expected_retrieval"],
                    "classified_by": route.classified_by,
                    "latency_ms": latency_ms,
                    "error": None,
                }
            )
        except Exception as exc:  # benchmark phai ghi loi thay vi dung ca lo
            results.append({**case, "error": f"{type(exc).__name__}: {exc}"})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="Khong goi OpenAI; chi kiem tra hop dong UI.",
    )
    args = parser.parse_args()

    contract = check_frontend_contract()
    cases = [] if args.contract_only else run_classifier_cases()
    completed = [case for case in cases if not case.get("error")]
    latencies = [case["latency_ms"] for case in completed]
    summary = {
        "frontend_contract_passed": contract["passed"],
        "classifier_cases": len(cases),
        "classifier_errors": len(cases) - len(completed),
        "category_accuracy": (
            round(sum(case["category_match"] for case in completed) / len(completed), 3)
            if completed
            else None
        ),
        "retrieval_decision_accuracy": (
            round(sum(case["retrieval_match"] for case in completed) / len(completed), 3)
            if completed
            else None
        ),
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
    }
    report = {
        "label": args.label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "frontend_contract": contract,
        "cases": cases,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / f"phase1_{args.label}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report: {output}")

    failed = not contract["passed"] or any(
        case.get("error") or not case["category_match"] or not case["retrieval_match"]
        for case in cases
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
