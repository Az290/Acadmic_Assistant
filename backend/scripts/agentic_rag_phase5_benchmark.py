"""Deterministic benchmark cho preference contract va memory bounds cua Phase 5."""

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.personalization.context_builder import (  # noqa: E402
    build_personalization_context,
    build_personalization_instruction,
)
from app.personalization.memory_service import compact_messages  # noqa: E402
from app.personalization.schemas import PreferencePublic  # noqa: E402

ROOT = Path(__file__).parent / "benchmarks"


class FakeMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


def main() -> int:
    dataset = json.loads((ROOT / "phase5_personalization_cases.json").read_text(encoding="utf-8"))
    rows = []
    latencies = []
    for case in dataset["cases"]:
        started = time.perf_counter()
        preference = PreferencePublic(**case["preference"])
        instruction = build_personalization_instruction(build_personalization_context(preference))
        latencies.append((time.perf_counter() - started) * 1000)
        passed = all(token in instruction for token in case["expected_tokens"]) and all(
            token not in instruction for token in case["forbidden_tokens"]
        )
        policy_preserved = not instruction or "khong thay doi evidence, policy, role hay quyen truy cap" in instruction
        rows.append({"id": case["id"], "passed": passed, "policy_preserved": policy_preserved})

    memory = compact_messages(
        [FakeMessage("user", "x" * 600), FakeMessage("assistant", "y" * 600)] * 10
    )
    report = {
        "summary": {
            "cases": len(rows),
            "preference_contract_rate": sum(r["passed"] for r in rows) / len(rows),
            "policy_boundary_rate": sum(r["policy_preserved"] for r in rows) / len(rows),
            "memory_bound_pass": len(memory) <= 2400,
            "median_builder_latency_ms": round(statistics.median(latencies), 4),
        },
        "cases": rows,
    }
    output = ROOT / "results" / "phase5_personalization.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if all(r["passed"] and r["policy_preserved"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
