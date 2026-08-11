"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, AnswerResponse, ApiError, QuizQuestionPublic } from "@/lib/api";

/**
 * Quiz ôn tập - làm 1 câu hỏi tại 1 thời điểm cho 1 concept cụ thể
 * (concept_id truyền qua query param, thường từ nút "Làm quiz ôn tập"
 * ở /mastery). Gọi thẳng 2 endpoint đã có sẵn ở backend từ trước
 * (POST /v1/learn/quiz, POST /v1/learn/answer) - trước đây CHƯA có UI
 * nào dùng tới, chỉ có logic backend.
 */
function QuizContent() {
  const params = useSearchParams();
  const conceptId = params.get("concept_id");

  const [question, setQuestion] = useState<QuizQuestionPublic | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadQuestion(id: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedIndex(null);
    api
      .post<QuizQuestionPublic>("/v1/learn/quiz", { concept_id: Number(id) })
      .then(setQuestion)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Không tải được câu hỏi quiz."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (conceptId) loadQuestion(conceptId);
    else {
      setLoading(false);
      setError("Thiếu concept_id - hãy vào từ trang Tiến độ học tập.");
    }
  }, [conceptId]);

  async function handleSubmit() {
    if (!question || selectedIndex === null) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post<AnswerResponse>("/v1/learn/answer", {
        quiz_question_id: question.id,
        selected_index: selectedIndex,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không nộp được đáp án.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
        Đang tải câu hỏi…
      </p>
    );
  }

  if (error && !question) {
    return (
      <p className="max-w-lg rounded-[9px] px-3 py-2 text-[13px]" style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}>
        {error}
      </p>
    );
  }

  if (!question) return null;

  return (
    <div className="max-w-lg">
      <div className="card">
        <h3 className="mb-3 text-[14px] font-semibold leading-relaxed">{question.question}</h3>

        <div className="space-y-2">
          {question.options.map((opt, i) => {
            const isSelected = selectedIndex === i;
            const isCorrect = result && i === result.correct_index;
            const isWrongPick = result && isSelected && !result.is_correct;
            let style: React.CSSProperties = { borderColor: "var(--border-strong)", background: "#fff" };
            if (result) {
              if (isCorrect) style = { borderColor: "var(--teal)", background: "var(--teal-bg)" };
              else if (isWrongPick) style = { borderColor: "var(--red)", background: "var(--red-bg)" };
            } else if (isSelected) {
              style = { borderColor: "var(--accent)", background: "var(--accent-bg)" };
            }
            return (
              <button
                key={i}
                onClick={() => !result && setSelectedIndex(i)}
                disabled={!!result}
                className="block w-full rounded-[9px] border px-3.5 py-2.5 text-left text-[13px] disabled:cursor-default"
                style={style}
              >
                {opt}
              </button>
            );
          })}
        </div>

        {error && (
          <p className="mt-2 text-[12px]" style={{ color: "var(--red-ink)" }}>
            {error}
          </p>
        )}

        {!result ? (
          <button
            onClick={handleSubmit}
            disabled={selectedIndex === null || submitting}
            className="mt-4 w-full rounded-[8px] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-50"
            style={{ background: "var(--accent)" }}
          >
            {submitting ? "Đang nộp…" : "Nộp đáp án"}
          </button>
        ) : (
          <>
            <div
              className="mt-4 rounded-[9px] border px-3.5 py-2.5 text-[12.5px] leading-relaxed"
              style={
                result.is_correct
                  ? { background: "var(--teal-bg)", borderColor: "#A8E6D5", color: "var(--teal-ink)" }
                  : { background: "var(--red-bg)", borderColor: "#EFC4C4", color: "var(--red-ink)" }
              }
            >
              <strong>{result.is_correct ? "Chính xác!" : "Chưa đúng."}</strong> {result.explanation}
            </div>
            <button
              onClick={() => conceptId && loadQuestion(conceptId)}
              className="mt-3 w-full rounded-[8px] px-4 py-2 text-[13px] font-semibold text-white"
              style={{ background: "var(--accent)" }}
            >
              Câu tiếp theo
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function QuizPage() {
  return (
    <Suspense fallback={null}>
      <QuizContent />
    </Suspense>
  );
}
