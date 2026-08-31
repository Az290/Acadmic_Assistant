"""Benchmark response quality Phase 4 qua HTTP that va LLM judge."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

BASE_URL = "http://127.0.0.1:8001"
DATASET = Path(__file__).parent / "benchmarks" / "phase4_response_cases.json"
RESULTS_DIR = Path(__file__).parent / "benchmarks" / "results"


class JudgeScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correctness: int = Field(ge=1, le=5)
    faithfulness: int = Field(ge=1, le=5)
    naturalness: int = Field(ge=1, le=5)
    follows_mode: bool
    reasoning: str = Field(max_length=500)


def judge(case: dict, answer: str) -> JudgeScore:
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    completion = client.chat.completions.parse(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": "Ban cham cau tra loi cua tro ly hoc thuat. Cham tung tieu chi: 5=dat day du, 4=tot co loi nho, 3=dat mot phan, 2=loi lon, 1=sai/khong dat. Correctness=khop expected. Faithfulness=khong them claim mau thuan hoac khong co trong expected. Naturalness=tu nhien, thang y. follows_mode chi dua tren Category: SOCRATIC_REQUEST phai goi mo, khong cho dap an va ket thuc bang mot cau hoi; cac category khac duoc tra loi truc tiep. Insufficient phai thua nhan thieu du lieu. Reasoning phai nhat quan voi diem; neu noi hoan toan dung thi khong duoc cho 1/5."},
            {"role": "user", "content": f"Question: {case['message']}\nExpected: {case['expected']}\nCategory: {case['expected_category']}\nActual: {answer}"},
        ],
        response_format=JudgeScore,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Judge khong tra structured output")
    return parsed


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--rejudge-report")
    args = parser.parse_args()
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = []
    if args.rejudge_report:
        previous = json.loads(Path(args.rejudge_report).read_text(encoding="utf-8"))
        cases_by_id = {case["id"]: case for case in dataset["cases"]}
        for old_row in previous["cases"]:
            score = await asyncio.to_thread(judge, cases_by_id[old_row["id"]], old_row["answer"])
            rows.append({**old_row, **score.model_dump()})
    else:
      async with httpx.AsyncClient(base_url=BASE_URL, timeout=90) as client:
        login = await client.post("/v1/auth/login", json=dataset["login"])
        login.raise_for_status()
        for name in ("access_token", "refresh_token"):
            if name in login.cookies:
                client.cookies.set(name, login.cookies[name])
        for case in dataset["cases"]:
            payload = {key: case[key] for key in ("message", "course_id", "force_category") if key in case}
            started = time.perf_counter()
            response = await client.post("/v1/chat", json=payload)
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            response.raise_for_status()
            body = response.json()
            score = await asyncio.to_thread(judge, case, body["answer"])
            citation_ok = bool(body.get("citations")) if case["citation_required"] else not body.get("citations")
            rows.append({
                "id": case["id"], "category": body["category"],
                "category_match": body["category"] == case["expected_category"],
                "citation_ok": citation_ok, "citations": body.get("citations", []),
                "answer": body["answer"], "latency_ms": latency_ms,
                **score.model_dump(),
            })
    summary = {
        "cases": len(rows),
        "category_accuracy": round(sum(row["category_match"] for row in rows) / len(rows), 3),
        "citation_contract_rate": round(sum(row["citation_ok"] for row in rows) / len(rows), 3),
        "avg_correctness": round(statistics.mean(row["correctness"] for row in rows), 2),
        "avg_faithfulness": round(statistics.mean(row["faithfulness"] for row in rows), 2),
        "avg_naturalness": round(statistics.mean(row["naturalness"] for row in rows), 2),
        "mode_follow_rate": round(sum(row["follows_mode"] for row in rows) / len(rows), 3),
        "median_latency_ms": round(statistics.median(row["latency_ms"] for row in rows), 1),
    }
    report = {"label": args.label, "created_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "cases": rows}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / f"phase4_{args.label}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
