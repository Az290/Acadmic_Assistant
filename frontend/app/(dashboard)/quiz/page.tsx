"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError, QuizSetResponse, SubmitAnswersResponse } from "@/lib/api";

/**
 * Quiz ôn tập - làm HẾT bộ câu hỏi rồi mới nộp một lần.
 *
 * TẠI SAO ĐỔI TỪ "1 câu / 1 lần nộp": nộp từng câu cắt vụn mạch làm
 * bài, không cho xem lại/đổi đáp án, và không có cảm giác đang làm một
 * bài kiểm tra thật. Giờ sinh viên đi qua từng câu (có chỉ báo "Câu
 * 2/5"), tự do quay lại sửa, rồi chốt một lần.
 *
 * Sau khi nộp: hiện đúng/sai từng câu, và MỌI câu (kể cả câu làm đúng)
 * đều có nút hỏi Nova giải thích - vì hiểu vì sao mình đúng cũng quan
 * trọng như biết vì sao mình sai.
 */
function QuizContent() {
  const params = useSearchParams();
  const conceptId = params.get("concept_id");

  const [quizSet, setQuizSet] = useState<QuizSetResponse | null>(null);
  // Đáp án đang chọn theo quiz_question_id - chưa nộp thì vẫn sửa được.
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [current, setCurrent] = useState(0);
  const [result, setResult] = useState<SubmitAnswersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadQuizSet(id: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    setAnswers({});
    setCurrent(0);
    api
      .post<QuizSetResponse>("/v1/learn/quiz-set", { concept_id: Number(id), num_questions: 5 })
      .then(setQuizSet)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Không tải được câu hỏi quiz."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (conceptId) loadQuizSet(conceptId);
    else {
      setLoading(false);
      setError("Thiếu concept_id - hãy vào từ trang Tiến độ học tập.");
    }
  }, [conceptId]);

  async function handleSubmitAll() {
    if (!quizSet) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post<SubmitAnswersResponse>("/v1/learn/answers", {
        answers: quizSet.questions.map((q) => ({
          quiz_question_id: q.id,
          selected_index: answers[q.id] ?? 0,
        })),
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không nộp được bài.");
    } finally {
      setSubmitting(false);
    }
  }

  /**
   * Gửi thẳng câu hỏi vào Nova kèm ĐỦ ngữ cảnh câu quiz - Nova không
   * phải đoán "câu nào", trả lời được ngay ở lượt đầu.
   */
  function askNova(questionText: string, options: string[], picked: number, correct: number) {
    const message =
      `Giải thích giúp mình câu quiz này:\n\n` +
      `${questionText}\n` +
      options.map((o, i) => `${String.fromCharCode(65 + i)}. ${o}`).join("\n") +
      `\n\nMình chọn: ${String.fromCharCode(65 + picked)}. ${options[picked]}` +
      `\nĐáp án đúng: ${String.fromCharCode(65 + correct)}. ${options[correct]}` +
      `\n\nVì sao đáp án đúng lại là như vậy?`;
    window.dispatchEvent(new CustomEvent("ask-nova", { detail: { question: message } }));
  }

  if (loading) {
    return (
      <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
        Đang tải câu hỏi…
      </p>
    );
  }

  if (error && !quizSet) {
    return (
      <p
        className="max-w-lg rounded-[9px] px-3 py-2 text-[13px]"
        style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
      >
        {error}
      </p>
    );
  }

  if (!quizSet) return null;

  const total = quizSet.questions.length;
  const answeredCount = quizSet.questions.filter((q) => answers[q.id] !== undefined).length;

  /* ---------- Sau khi nộp: bảng kết quả từng câu ---------- */
  if (result) {
    return (
      <div className="max-w-2xl">
        <div
          className="card mb-4 text-center"
          style={
            result.score === result.total
              ? { background: "var(--teal-bg)", borderColor: "#A8E6D5" }
              : undefined
          }
        >
          <div className="text-[26px] font-bold" style={{ color: "var(--accent-ink)" }}>
            {result.score}/{result.total}
          </div>
          <p className="text-support mt-1">
            {result.score === result.total
              ? "Tuyệt vời — bạn làm đúng toàn bộ."
              : `Bạn làm đúng ${result.score} trên ${result.total} câu. Xem lại các câu bên dưới nhé.`}
            {result.mastered && " Khái niệm này đã được đánh dấu là đã nắm vững."}
          </p>
        </div>

        <div className="space-y-3">
          {result.results.map((r, i) => (
            <div
              key={r.quiz_question_id}
              className="card"
              style={{
                borderColor: r.is_correct ? "#A8E6D5" : "#EFC4C4",
                background: r.is_correct ? "var(--teal-bg)" : "var(--red-bg)",
              }}
            >
              <div className="mb-1 flex items-center gap-2">
                <span
                  className="rounded-full px-2 py-0.5 text-[10.5px] font-bold"
                  style={{
                    background: r.is_correct ? "var(--teal)" : "var(--red)",
                    color: "#fff",
                  }}
                >
                  {r.is_correct ? "Đúng" : "Sai"}
                </span>
                <span className="text-[11px]" style={{ color: "var(--ink-soft)" }}>
                  Câu {i + 1}/{result.total}
                </span>
              </div>

              <div className="mb-2 text-[13px] font-semibold leading-relaxed">{r.question}</div>

              <div className="space-y-1.5">
                {r.options.map((opt, idx) => {
                  const isCorrect = idx === r.correct_index;
                  const isPicked = idx === r.selected_index;
                  return (
                    <div
                      key={idx}
                      className="rounded-[8px] border px-3 py-1.5 text-[12.5px]"
                      style={{
                        borderColor: isCorrect
                          ? "var(--teal)"
                          : isPicked
                            ? "var(--red)"
                            : "var(--border)",
                        background: "#fff",
                      }}
                    >
                      {String.fromCharCode(65 + idx)}. {opt}
                      {isCorrect && (
                        <span className="ml-1.5 font-semibold" style={{ color: "var(--teal-ink)" }}>
                          ✓ đáp án đúng
                        </span>
                      )}
                      {isPicked && !isCorrect && (
                        <span className="ml-1.5 font-semibold" style={{ color: "var(--red-ink)" }}>
                          ← bạn chọn
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>

              {r.explanation && (
                <p className="mt-2 text-[12px] leading-relaxed" style={{ color: "var(--ink-soft)" }}>
                  {r.explanation}
                </p>
              )}

              {/* Hỏi Nova được cho MỌI câu, không chỉ câu sai - hiểu vì
                  sao mình đúng cũng quan trọng như biết vì sao mình sai. */}
              <button
                onClick={() => askNova(r.question, r.options, r.selected_index, r.correct_index)}
                className="mt-2.5 rounded-[7px] px-3 py-1.5 text-[12px] font-semibold text-white"
                style={{ background: "var(--accent)" }}
              >
                Hỏi Nova giải thích câu này
              </button>
            </div>
          ))}
        </div>

        <button
          onClick={() => conceptId && loadQuizSet(conceptId)}
          className="mt-4 w-full rounded-[8px] border px-4 py-2 text-[13px] font-semibold"
          style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
        >
          Làm bộ câu hỏi khác
        </button>
      </div>
    );
  }

  /* ---------- Đang làm bài ---------- */
  const question = quizSet.questions[current];
  const picked = answers[question.id];

  return (
    <div className="max-w-2xl">
      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[11.5px] font-semibold" style={{ color: "var(--ink-soft)" }}>
            Câu {current + 1}/{total} · {quizSet.concept_name}
          </span>
          <span className="text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
            Đã trả lời {answeredCount}/{total}
          </span>
        </div>

        {/* Thanh tiến độ - nhìn là biết còn bao nhiêu câu nữa */}
        <div className="mb-4 h-1.5 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
          <div
            className="h-full rounded-full"
            style={{
              width: `${((current + 1) / total) * 100}%`,
              background: "var(--accent)",
              transition: "width var(--motion-base) var(--ease)",
            }}
          />
        </div>

        <h3 className="mb-3 text-[14px] font-semibold leading-relaxed">{question.question}</h3>

        <div className="space-y-2">
          {question.options.map((opt, i) => (
            <button
              key={i}
              onClick={() => setAnswers((prev) => ({ ...prev, [question.id]: i }))}
              className="block w-full rounded-[9px] border px-3.5 py-2.5 text-left text-[13px]"
              style={
                picked === i
                  ? { borderColor: "var(--accent)", background: "var(--accent-bg)" }
                  : { borderColor: "var(--border-strong)", background: "#fff" }
              }
            >
              {String.fromCharCode(65 + i)}. {opt}
            </button>
          ))}
        </div>

        {error && (
          <p className="mt-2 text-[12px]" style={{ color: "var(--red-ink)" }}>
            {error}
          </p>
        )}

        <div className="mt-4 flex items-center gap-2">
          <button
            onClick={() => setCurrent((c) => Math.max(0, c - 1))}
            disabled={current === 0}
            className="rounded-[8px] border px-4 py-2 text-[13px] font-semibold disabled:opacity-40"
            style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
          >
            ← Trước
          </button>

          {current < total - 1 ? (
            <button
              onClick={() => setCurrent((c) => Math.min(total - 1, c + 1))}
              className="flex-1 rounded-[8px] px-4 py-2 text-[13px] font-semibold text-white"
              style={{ background: "var(--accent)" }}
            >
              Câu tiếp theo →
            </button>
          ) : (
            <button
              onClick={handleSubmitAll}
              disabled={submitting || answeredCount < total}
              className="flex-1 rounded-[8px] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-50"
              style={{ background: "var(--teal)" }}
              title={answeredCount < total ? "Hãy trả lời hết các câu trước khi nộp" : undefined}
            >
              {submitting ? "Đang nộp…" : `Nộp bài (${answeredCount}/${total})`}
            </button>
          )}
        </div>

        {/* Nhảy nhanh tới câu bất kỳ - thuận tiện khi muốn quay lại sửa
            câu còn phân vân, không phải bấm "Trước" nhiều lần. */}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {quizSet.questions.map((q, i) => (
            <button
              key={q.id}
              onClick={() => setCurrent(i)}
              className="h-7 w-7 rounded-[6px] border text-[11.5px] font-semibold"
              style={
                i === current
                  ? { borderColor: "var(--accent)", background: "var(--accent)", color: "#fff" }
                  : answers[q.id] !== undefined
                    ? { borderColor: "var(--accent)", background: "var(--accent-bg)", color: "var(--accent-ink)" }
                    : { borderColor: "var(--border-strong)", color: "var(--ink-faint)" }
              }
              title={answers[q.id] !== undefined ? "Đã trả lời" : "Chưa trả lời"}
            >
              {i + 1}
            </button>
          ))}
        </div>
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
