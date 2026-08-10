"""
Eval - đo chất lượng Academic Agent bằng bộ câu hỏi mẫu (scripts/eval_dataset.json),
chạy qua HTTP THẬT (không phải gọi hàm Python trực tiếp) - đúng nguyên tắc dự án:
mọi test phải đi qua đúng đường mà người dùng thật sẽ đi qua (FastAPI, Guardrail,
Router, Retrieval, rate limit...), không bỏ qua tầng nào.

3 tiêu chí đo, MỤC ĐÍCH KHÁC NHAU nên CÁCH ĐO khác nhau:

1. Router category - so khớp CHUỖI với nhãn đã gán tay trong dataset. Rẻ, khách
   quan, không cần LLM chấm (đúng/sai rõ ràng, không mơ hồ).

2. Retrieval (Recall@K) - "chunk_id ĐÚNG có nằm trong top-K kết quả Hybrid Search
   không?". Đo bằng số liệu cứng, không cần LLM - chỉ cần biết chunk nào đã được
   dùng làm context (lấy từ trường `citations` trong response).

3. Chất lượng câu trả lời cuối - đây là phần CHỦ QUAN (đúng NGHĨA, không phải
   đúng TỪ), so khớp chuỗi không đo được ("Concatenation nối chuỗi bằng dấu +"
   và "Toán tử + dùng để ghép 2 string lại" nói CÙNG 1 Ý nhưng không khớp chuỗi
   nào) - dùng LLM-as-judge (gpt-4o-mini, RẺ, đã dùng sẵn trong dự án) để chấm
   theo thang 1-5, kèm lý do ngắn giải thích điểm số đó.

Chạy: python scripts/eval.py
Yêu cầu: backend đang chạy ở BASE_URL (mặc định http://localhost:8001).
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from openai import OpenAI

# Console mặc định trên Windows dùng codepage cp1258/cp437 (không phải
# UTF-8) - print() tiếng Việt có dấu sẽ crash với UnicodeEncodeError nếu
# không ép lại encoding của stdout. reconfigure() chỉ có từ Python 3.7+,
# an toàn dùng ở đây (dự án đã yêu cầu Python 3.11+).
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

BASE_URL = "http://localhost:8001"
DATASET_PATH = Path(__file__).parent / "eval_dataset.json"
REPORT_PATH = Path(__file__).parent / "eval_report.json"

_settings = get_settings()
_judge_client = OpenAI(api_key=_settings.openai_api_key)
JUDGE_MODEL = "gpt-4o-mini"

_JUDGE_SYSTEM_PROMPT = """Bạn là giám khảo chấm chất lượng câu trả lời của 1 trợ lý học thuật AI.
Cho bạn: câu hỏi, tóm tắt nội dung ĐÚNG mong đợi (ground truth), và câu trả lời THẬT mà hệ thống đã sinh ra.

Chấm điểm 1-5 theo 3 tiêu chí:
- Đúng nội dung: có khớp ý với ground truth không (không cần khớp từng chữ, chỉ cần đúng Ý)
- Không bịa đặt: có tự thêm thông tin KHÔNG có trong ground truth/tài liệu không (nếu ground truth nói "không tìm thấy", câu trả lời PHẢI thừa nhận không biết, KHÔNG được tự bịa ra đáp án)
- Phù hợp category: nếu category là SOCRATIC_REQUEST, câu trả lời phải mang tính gợi mở/dẫn dắt, KHÔNG đưa đáp án trực tiếp

Trả về JSON: {"score": <1-5>, "reasoning": "<lý do ngắn gọn 1-2 câu>"}"""


@dataclass
class CaseResult:
    id: str
    expected_category: str
    actual_category: str | None = None
    category_match: bool | None = None
    expected_chunk_ids: list[int] = field(default_factory=list)
    actual_chunk_ids: list[int] = field(default_factory=list)
    recall_at_k: float | None = None  # None nếu case này không cần retrieval (chitchat/off-topic/blocked)
    blocked_expected: bool = False
    blocked_actual: bool = False
    answer: str = ""
    judge_score: int | None = None
    judge_reasoning: str = ""
    latency_s: float = 0.0
    error: str | None = None


def compute_recall_at_k(expected: list[int], actual: list[int]) -> float | None:
    """
    Recall@K: trong số chunk ĐÚNG (expected), bao nhiêu % xuất hiện trong kết
    quả Retrieval thật đã dùng để trả lời (actual). K ở đây là số lượng chunk
    Hybrid Search thực sự trả về cho câu hỏi đó (không phải hằng số cố định) -
    đo đúng câu hỏi "hệ thống có TÌM THẤY tài liệu đúng không", không đánh giá
    thứ hạng cụ thể trong top-K (đơn giản hơn NDCG, đủ dùng cho MVP).
    """
    if not expected:
        # Không có chunk "đúng" kỳ vọng - áp dụng cho 2 trường hợp Ý NGHĨA
        # KHÁC NHAU: (a) câu hỏi không cần retrieval (chitchat/off-topic,
        # không nằm trong nhánh này vì recall_at_k=None ở run_case), hoặc
        # (b) câu hỏi CẦN retrieval nhưng tài liệu THẬT SỰ không có thông
        # tin (case "hallucination test") - ở (b), retrieval trả về CÀNG
        # ÍT chunk hoặc chunk không liên quan càng đúng ý đồ (không thể đo
        # "đúng/sai" bằng chunk_id vì không có gì để khớp) - trả None để
        # KHÔNG tính vào avg_recall (tránh làm sai lệch số liệu tổng), việc
        # đánh giá case này giao hẳn cho LLM-judge (có bịa đặt hay không).
        return None
    hits = sum(1 for cid in expected if cid in actual)
    return hits / len(expected)


def judge_answer(question: str, expected_summary: str, actual_answer: str, category: str) -> tuple[int | None, str]:
    try:
        response = _judge_client.chat.completions.create(
            model=JUDGE_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Category: {category}\n"
                        f"Câu hỏi: {question}\n"
                        f"Ground truth (tóm tắt): {expected_summary}\n"
                        f"Câu trả lời THẬT của hệ thống: {actual_answer}"
                    ),
                },
            ],
        )
        parsed = json.loads(response.choices[0].message.content)
        return int(parsed["score"]), parsed.get("reasoning", "")
    except Exception as e:  # LLM-judge lỗi KHÔNG được làm sập cả lượt eval - ghi nhận lỗi, tiếp tục case khác
        return None, f"Lỗi khi chấm: {e}"


async def run_case(client: httpx.AsyncClient, case: dict) -> CaseResult:
    result = CaseResult(
        id=case["id"],
        expected_category=case["category"],
        expected_chunk_ids=case["expected_chunk_ids"],
        blocked_expected=(case["category"] == "BLOCKED"),
    )

    start = time.time()
    try:
        response = await client.post("/v1/chat", json={"message": case["message"]})
        result.latency_s = time.time() - start

        if response.status_code != 200:
            result.error = f"HTTP {response.status_code}: {response.text[:200]}"
            return result

        body = response.json()
        result.blocked_actual = body.get("blocked", False)
        result.actual_category = body.get("category")
        result.answer = body.get("answer", "")
        result.actual_chunk_ids = [c["chunk_id"] for c in body.get("citations", [])]

        # Case BLOCKED: đúng/sai chỉ phụ thuộc có bị chặn hay không, KHÔNG so
        # category (Guardrail chặn thì category luôn là "BLOCKED" cố định ở
        # backend, không có ý nghĩa so khớp thêm).
        if result.blocked_expected:
            result.category_match = result.blocked_actual
        else:
            result.category_match = (result.actual_category == result.expected_category) and not result.blocked_actual

        if not result.blocked_expected:
            result.recall_at_k = compute_recall_at_k(result.expected_chunk_ids, result.actual_chunk_ids)
            result.judge_score, result.judge_reasoning = judge_answer(
                case["message"], case["expected_answer_summary"], result.answer, case["category"]
            )
    except Exception as e:
        result.error = str(e)
        result.latency_s = time.time() - start

    return result


async def main():
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        login = await client.post("/v1/auth/login", json=dataset["login"])
        if login.status_code != 200:
            print(f"LỖI: không đăng nhập được ({login.status_code}): {login.text}")
            return
        for name in ("access_token", "refresh_token"):
            if name in login.cookies:
                client.cookies.set(name, login.cookies[name])

        print(f"Đăng nhập OK. Chạy {len(dataset['cases'])} câu hỏi mẫu tuần tự...\n")

        results: list[CaseResult] = []
        for case in dataset["cases"]:
            r = await run_case(client, case)
            results.append(r)
            status = "OK" if r.error is None else "LỖI"
            print(f"[{status}] {r.id} ({r.latency_s:.1f}s)" + (f" - {r.error}" if r.error else ""))

    # ---- Tổng hợp ----
    n = len(results)
    n_errors = sum(1 for r in results if r.error is not None)
    valid = [r for r in results if r.error is None]

    category_matches = sum(1 for r in valid if r.category_match)
    category_accuracy = category_matches / len(valid) if valid else 0.0

    recall_cases = [r for r in valid if r.recall_at_k is not None]
    avg_recall = sum(r.recall_at_k for r in recall_cases) / len(recall_cases) if recall_cases else None

    judge_cases = [r for r in valid if r.judge_score is not None]
    avg_judge_score = sum(r.judge_score for r in judge_cases) / len(judge_cases) if judge_cases else None

    report = {
        "summary": {
            "total_cases": n,
            "errors": n_errors,
            "category_accuracy": round(category_accuracy, 3),
            "avg_recall_at_k": round(avg_recall, 3) if avg_recall is not None else None,
            "avg_judge_score": round(avg_judge_score, 2) if avg_judge_score is not None else None,
            "judge_cases_scored": len(judge_cases),
        },
        "cases": [
            {
                "id": r.id,
                "expected_category": r.expected_category,
                "actual_category": r.actual_category,
                "category_match": r.category_match,
                "expected_chunk_ids": r.expected_chunk_ids,
                "actual_chunk_ids": r.actual_chunk_ids,
                "recall_at_k": r.recall_at_k,
                "judge_score": r.judge_score,
                "judge_reasoning": r.judge_reasoning,
                "answer_preview": (r.answer[:200] + "…") if len(r.answer) > 200 else r.answer,
                "latency_s": round(r.latency_s, 2),
                "error": r.error,
            }
            for r in results
        ],
    }

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("TỔNG KẾT")
    print("=" * 60)
    print(f"Tổng số câu: {n} (lỗi: {n_errors})")
    print(f"Router category accuracy: {category_accuracy:.1%}")
    print(f"Retrieval avg Recall@K: {avg_recall:.1%}" if avg_recall is not None else "Retrieval: không có case nào")
    print(f"LLM-judge avg score (1-5): {avg_judge_score:.2f}" if avg_judge_score is not None else "Judge: không có case nào")
    print(f"\nBáo cáo chi tiết đã lưu: {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
