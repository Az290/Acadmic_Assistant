"use client";

import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  AssignmentDetail,
  AssignmentPublic,
  AssignmentResults,
  ConceptPublic,
  CoursePublic,
  SubmitAssignmentResponse,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import WeakestConceptToast from "@/components/WeakestConceptToast";

/**
 * Trang bài tập - DÙNG CHUNG cho cả 2 vai trò, hiển thị khác nhau:
 * - Giảng viên: giao bài mới + xem kết quả cả lớp
 * - Sinh viên: làm bài + xem điểm của mình
 *
 * Gộp 1 trang thay vì tách 2 vì phần lớn nội dung (danh sách bài tập)
 * giống hệt nhau, chỉ khác thao tác đi kèm.
 */
export default function AssignmentsPage() {
  const { user } = useAuth();
  const isInstructor = user?.role === "INSTRUCTOR" || user?.role === "ADMIN";

  const [courses, setCourses] = useState<CoursePublic[]>([]);
  const [courseId, setCourseId] = useState<number | null>(null);
  const [assignments, setAssignments] = useState<AssignmentPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Giao bài (giảng viên)
  const [concepts, setConcepts] = useState<ConceptPublic[]>([]);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [selectedConcepts, setSelectedConcepts] = useState<number[]>([]);

  // Làm bài (sinh viên)
  const [doing, setDoing] = useState<AssignmentDetail | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [result, setResult] = useState<SubmitAssignmentResponse | null>(null);

  // Xem kết quả (giảng viên)
  const [results, setResults] = useState<AssignmentResults | null>(null);

  useEffect(() => {
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then((list) => {
        setCourses(list);
        if (list.length > 0) setCourseId(list[0].id);
      })
      .catch(() => setCourses([]));
  }, []);

  async function loadAssignments(cid: number) {
    setLoading(true);
    setError(null);
    try {
      setAssignments(await api.get<AssignmentPublic[]>(`/v1/assignments?course_id=${cid}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không tải được danh sách bài tập.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (courseId === null) return;
    loadAssignments(courseId);
    if (isInstructor) {
      api
        .get<ConceptPublic[]>(`/v1/concepts?course_id=${courseId}`)
        .then(setConcepts)
        .catch(() => setConcepts([]));
    }
  }, [courseId, isInstructor]);

  async function handleCreate() {
    if (courseId === null || !newTitle.trim() || selectedConcepts.length === 0) return;
    setCreating(true);
    setError(null);
    try {
      await api.post("/v1/assignments", {
        course_id: courseId,
        title: newTitle.trim(),
        concept_ids: selectedConcepts,
      });
      setNewTitle("");
      setSelectedConcepts([]);
      await loadAssignments(courseId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không giao được bài tập.");
    } finally {
      setCreating(false);
    }
  }

  async function startDoing(assignmentId: number) {
    setError(null);
    setResult(null);
    setResults(null);
    try {
      const detail = await api.get<AssignmentDetail>(`/v1/assignments/${assignmentId}`);
      setDoing(detail);
      setAnswers({});
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không mở được bài tập.");
    }
  }

  async function handleSubmit() {
    if (doing === null) return;
    setError(null);
    try {
      const res = await api.post<SubmitAssignmentResponse>(`/v1/assignments/${doing.id}/submit`, {
        answers: Object.entries(answers).map(([qid, idx]) => ({
          quiz_question_id: Number(qid),
          selected_index: idx,
        })),
      });
      setResult(res);
      setDoing(null);
      if (courseId !== null) await loadAssignments(courseId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không nộp được bài.");
    }
  }

  async function viewResults(assignmentId: number) {
    setError(null);
    setDoing(null);
    setResult(null);
    try {
      setResults(await api.get<AssignmentResults>(`/v1/assignments/${assignmentId}/results`));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không xem được kết quả.");
    }
  }

  return (
    <div className="max-w-4xl">
      {!isInstructor && <WeakestConceptToast />}

      {courses.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {courses.map((c) => (
            <button
              key={c.id}
              onClick={() => setCourseId(c.id)}
              className="rounded-full border px-3 py-1.5 text-xs font-semibold"
              style={
                c.id === courseId
                  ? { background: "var(--ink)", color: "#fff", borderColor: "var(--ink)" }
                  : { background: "#fff", borderColor: "var(--border-strong)", color: "var(--ink)" }
              }
            >
              {c.code}
            </button>
          ))}
        </div>
      )}

      {error && (
        <p
          className="mb-3 rounded-[9px] px-3 py-2 text-[13px]"
          style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
        >
          {error}
        </p>
      )}

      {/* ----- Giảng viên: giao bài mới ----- */}
      {isInstructor && !doing && !results && (
        <div className="card mb-4">
          <h3 className="mb-2 text-[12.5px] font-bold">Giao bài tập mới</h3>
          {concepts.length === 0 ? (
            <p className="text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
              Lớp này chưa có khái niệm nào. Tạo khái niệm trước để hệ thống ra đề.
            </p>
          ) : (
            <>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Tên bài tập, vd: Kiểm tra giữa kỳ"
                className="mb-2 w-full rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
                style={{ borderColor: "var(--border-strong)" }}
              />
              <div className="mb-2 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                Chọn khái niệm cần kiểm tra (mỗi khái niệm 1 câu hỏi):
              </div>
              <div className="mb-2 flex flex-wrap gap-1.5">
                {concepts.map((c) => {
                  const picked = selectedConcepts.includes(c.id);
                  return (
                    <button
                      key={c.id}
                      onClick={() =>
                        setSelectedConcepts((prev) =>
                          picked ? prev.filter((id) => id !== c.id) : [...prev, c.id]
                        )
                      }
                      className="rounded-full border px-2.5 py-1 text-[11px] font-semibold"
                      style={
                        picked
                          ? { background: "var(--accent)", color: "#fff", borderColor: "var(--accent)" }
                          : { background: "#fff", borderColor: "var(--border-strong)", color: "var(--ink-soft)" }
                      }
                    >
                      {c.name}
                    </button>
                  );
                })}
              </div>
              <button
                onClick={handleCreate}
                disabled={creating || !newTitle.trim() || selectedConcepts.length === 0}
                className="rounded-[7px] px-4 py-2 text-[12.3px] font-semibold text-white disabled:opacity-50"
                style={{ background: "var(--accent)" }}
              >
                {creating ? "Đang tạo đề…" : `Giao bài (${selectedConcepts.length} câu)`}
              </button>
            </>
          )}
        </div>
      )}

      {/* ----- Sinh viên: đang làm bài ----- */}
      {doing && (
        <div className="card mb-4">
          <h3 className="mb-1 text-[13px] font-bold">{doing.title}</h3>
          {doing.description && (
            <p className="mb-3 text-[12px]" style={{ color: "var(--ink-soft)" }}>
              {doing.description}
            </p>
          )}
          {doing.questions.map((q, i) => (
            <div key={q.quiz_question_id} className="mb-4">
              <div className="mb-1.5 text-[12.5px] font-semibold">
                Câu {i + 1}. {q.question}
              </div>
              {q.options.map((opt, idx) => (
                <label
                  key={idx}
                  className="mb-1 flex cursor-pointer items-start gap-2 rounded-[7px] border px-2.5 py-1.5 text-[12px]"
                  style={{
                    borderColor:
                      answers[q.quiz_question_id] === idx ? "var(--accent)" : "var(--border)",
                    background: answers[q.quiz_question_id] === idx ? "var(--accent-bg)" : "#fff",
                  }}
                >
                  <input
                    type="radio"
                    name={`q-${q.quiz_question_id}`}
                    checked={answers[q.quiz_question_id] === idx}
                    onChange={() =>
                      setAnswers((prev) => ({ ...prev, [q.quiz_question_id]: idx }))
                    }
                  />
                  <span>{opt}</span>
                </label>
              ))}
            </div>
          ))}
          <div className="flex gap-2">
            <button
              onClick={handleSubmit}
              disabled={Object.keys(answers).length === 0}
              className="rounded-[7px] px-4 py-2 text-[12.3px] font-semibold text-white disabled:opacity-50"
              style={{ background: "var(--teal)" }}
            >
              Nộp bài
            </button>
            <button
              onClick={() => setDoing(null)}
              className="rounded-[7px] border px-4 py-2 text-[12.3px] font-semibold"
              style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
            >
              Huỷ
            </button>
          </div>
        </div>
      )}

      {/* ----- Sinh viên: kết quả vừa nộp ----- */}
      {result && (
        <div className="card mb-4">
          <h3 className="mb-2 text-[13px] font-bold">
            Kết quả: {result.score}/{result.total} câu đúng
          </h3>
          {result.results.map((r, i) => (
            <div
              key={r.quiz_question_id}
              className="mb-2 rounded-[9px] border px-3 py-2 text-[12px]"
              style={{
                background: r.is_correct ? "var(--teal-bg)" : "var(--red-bg)",
                borderColor: r.is_correct ? "#A8E6D5" : "#EFC4C4",
                color: r.is_correct ? "var(--teal-ink)" : "var(--red-ink)",
              }}
            >
              <strong>
                Câu {i + 1}: {r.is_correct ? "Đúng" : "Sai"}
              </strong>
              <div className="mt-1">{r.explanation}</div>
            </div>
          ))}
          <button
            onClick={() => setResult(null)}
            className="rounded-[7px] border px-4 py-1.5 text-[12.3px] font-semibold"
            style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
          >
            Đóng
          </button>
        </div>
      )}

      {/* ----- Giảng viên: kết quả cả lớp ----- */}
      {results && (
        <div className="card mb-4">
          <h3 className="mb-2 text-[13px] font-bold">Kết quả: {results.title}</h3>
          <div className="mb-3 text-[12px]" style={{ color: "var(--ink-soft)" }}>
            Đã nộp: {results.submitted_count}/{results.enrolled_count} sinh viên · Điểm trung bình:{" "}
            {results.average_score.toFixed(1)}/{results.total_questions}
          </div>

          {results.concept_difficulty.length > 0 && (
            <>
              <h4 className="mb-1.5 text-[12px] font-bold">Khái niệm cả lớp yếu nhất</h4>
              {results.concept_difficulty.map((c) => (
                <div key={c.concept_id} className="mb-2">
                  <div className="flex justify-between text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                    <span>{c.concept_name}</span>
                    <span>
                      {c.correct_count}/{c.total_count} đúng ({Math.round(c.accuracy * 100)}%)
                    </span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-md" style={{ background: "#E8EAF0" }}>
                    <div
                      className="h-full rounded-md"
                      style={{
                        width: `${Math.round(c.accuracy * 100)}%`,
                        background: c.accuracy < 0.5 ? "var(--red)" : "var(--teal)",
                      }}
                    />
                  </div>
                </div>
              ))}
            </>
          )}

          {results.students.length > 0 && (
            <>
              <h4 className="mb-1.5 mt-3 text-[12px] font-bold">Điểm từng sinh viên</h4>
              {results.students.map((s) => (
                <div
                  key={s.user_id}
                  className="flex justify-between border-b py-1.5 text-[12.5px] last:border-0"
                  style={{ borderColor: "var(--border)" }}
                >
                  <span>{s.full_name}</span>
                  <span className="font-mono font-semibold">
                    {s.score}/{s.total}
                  </span>
                </div>
              ))}
            </>
          )}

          <button
            onClick={() => setResults(null)}
            className="mt-3 rounded-[7px] border px-4 py-1.5 text-[12.3px] font-semibold"
            style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
          >
            Đóng
          </button>
        </div>
      )}

      {/* ----- Danh sách bài tập ----- */}
      {!doing && (
        <>
          {loading && (
            <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
              Đang tải…
            </p>
          )}
          {!loading && assignments.length === 0 && (
            <div className="card">
              <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
                Lớp này chưa có bài tập nào.
              </p>
            </div>
          )}
          <div className="space-y-2.5">
            {assignments.map((a) => (
              <div key={a.id} className="card">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold">{a.title}</div>
                    <div className="text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                      {a.question_count} câu
                      {a.submitted && ` · Đã nộp: ${a.my_score}/${a.my_total}`}
                    </div>
                  </div>
                  {isInstructor ? (
                    <button
                      onClick={() => viewResults(a.id)}
                      className="whitespace-nowrap rounded-[7px] border px-3 py-1.5 text-[12.3px] font-semibold"
                      style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                    >
                      Xem kết quả
                    </button>
                  ) : a.submitted ? (
                    <span
                      className="whitespace-nowrap rounded-full px-2.5 py-[3px] text-[10.5px] font-bold"
                      style={{ background: "var(--teal-bg)", color: "var(--teal-ink)" }}
                    >
                      Đã nộp
                    </span>
                  ) : (
                    <button
                      onClick={() => startDoing(a.id)}
                      className="whitespace-nowrap rounded-[7px] px-4 py-1.5 text-[12.3px] font-semibold text-white"
                      style={{ background: "var(--accent)" }}
                    >
                      Làm bài
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
