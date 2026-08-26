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
  CreateConceptRequest,
  GeneratedQuizQuestion,
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

  // Giao bài (giảng viên) - luồng mới 2 bước: (1) chọn khái niệm + số câu
  // -> sinh nháp, (2) xem/sửa/bỏ câu rồi mới thực sự giao.
  const [concepts, setConcepts] = useState<ConceptPublic[]>([]);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [selectedConcepts, setSelectedConcepts] = useState<number[]>([]);
  const [numPerConcept, setNumPerConcept] = useState(1);
  const [generating, setGenerating] = useState(false);
  const [draftQuestions, setDraftQuestions] = useState<GeneratedQuizQuestion[] | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<{
    question: string;
    options: string[];
    correct_index: number;
    explanation: string;
  } | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  // Tạo khái niệm mới (giảng viên) - form thu gọn/mở tuỳ concepts.length,
  // xem effect load bên dưới.
  const [showConceptForm, setShowConceptForm] = useState(false);
  const [conceptName, setConceptName] = useState("");
  const [conceptComplexity, setConceptComplexity] = useState(3);
  const [creatingConcept, setCreatingConcept] = useState(false);

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

  async function loadConcepts(cid: number) {
    try {
      const list = await api.get<ConceptPublic[]>(`/v1/concepts?course_id=${cid}`);
      setConcepts(list);
      // Rỗng thì mở sẵn form (đúng như thông báo hướng dẫn cũ), có rồi
      // thì thu gọn lại - giảng viên bấm "+ Thêm khái niệm" khi cần.
      setShowConceptForm(list.length === 0);
    } catch {
      setConcepts([]);
    }
  }

  useEffect(() => {
    if (courseId === null) return;
    loadAssignments(courseId);
    if (isInstructor) loadConcepts(courseId);
  }, [courseId, isInstructor]);

  async function handleCreateConcept() {
    if (courseId === null || !conceptName.trim()) return;
    setCreatingConcept(true);
    setError(null);
    try {
      const body: CreateConceptRequest = {
        course_id: courseId,
        name: conceptName.trim(),
        complexity: conceptComplexity,
        prerequisites: [],
      };
      await api.post<ConceptPublic>("/v1/concepts", body);
      setConceptName("");
      setConceptComplexity(3);
      await loadConcepts(courseId);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không tạo được khái niệm.");
    } finally {
      setCreatingConcept(false);
    }
  }

  async function handleGenerate() {
    if (courseId === null || selectedConcepts.length === 0) return;
    setGenerating(true);
    setError(null);
    try {
      const questions = await api.post<GeneratedQuizQuestion[]>(
        "/v1/assignments/generate-questions",
        {
          course_id: courseId,
          concept_ids: selectedConcepts,
          num_questions_per_concept: numPerConcept,
        }
      );
      setDraftQuestions(questions);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không sinh được câu hỏi.");
    } finally {
      setGenerating(false);
    }
  }

  function handleResetDraft() {
    setDraftQuestions(null);
    setEditingId(null);
    setEditForm(null);
  }

  function startEditDraft(q: GeneratedQuizQuestion) {
    setEditingId(q.id);
    setEditForm({
      question: q.question,
      options: [...q.options],
      correct_index: q.correct_index,
      explanation: q.explanation,
    });
  }

  async function handleSaveEdit(id: number) {
    if (editForm === null) return;
    setSavingEdit(true);
    setError(null);
    try {
      const updated = await api.patch<GeneratedQuizQuestion>(`/v1/quiz-questions/${id}`, editForm);
      setDraftQuestions((prev) => (prev ? prev.map((q) => (q.id === id ? updated : q)) : prev));
      setEditingId(null);
      setEditForm(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không sửa được câu hỏi.");
    } finally {
      setSavingEdit(false);
    }
  }

  function handleRemoveDraft(id: number) {
    // Chỉ loại khỏi danh sách SẮP giao, KHÔNG xoá khỏi DB - an toàn hơn,
    // và đơn giản hơn (không cần endpoint xoá riêng).
    setDraftQuestions((prev) => (prev ? prev.filter((q) => q.id !== id) : prev));
  }

  async function handleAssign() {
    if (courseId === null || !newTitle.trim() || !draftQuestions || draftQuestions.length === 0) return;
    setCreating(true);
    setError(null);
    try {
      await api.post("/v1/assignments", {
        course_id: courseId,
        title: newTitle.trim(),
        quiz_question_ids: draftQuestions.map((q) => q.id),
      });
      setNewTitle("");
      setSelectedConcepts([]);
      handleResetDraft();
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

  const activeCourse = courses.find((course) => course.id === courseId);

  return (
    <div className="assignments-page max-w-4xl">
      {!isInstructor && <WeakestConceptToast />}

      <section className="page-visual-hero page-visual-hero--assignments">
        <div><span className="page-visual-hero__eyebrow">{activeCourse?.code ?? "Bài tập"}</span><h2>{isInstructor ? "Thiết kế hoạt động luyện tập" : "Luyện tập để tiến bộ mỗi ngày"}</h2><p>{isInstructor ? "Tạo bài kiểm tra theo khái niệm và quan sát kết quả của cả lớp." : "Hoàn thành bài tập, xem giải thích và củng cố phần kiến thức còn yếu."}</p></div>
        <div className="assignment-visual" aria-hidden="true"><span>✓</span><i></i><i></i><i></i></div>
      </section>

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

      {/* ----- Giảng viên: tạo khái niệm mới -----
          Đặt TRƯỚC form giao bài vì phải có khái niệm thì mới giao bài
          được - luôn hiện (không chỉ khi rỗng) vì giảng viên có thể
          muốn thêm khái niệm mới bất cứ lúc nào, chỉ thu gọn lại khi
          lớp đã có sẵn khái niệm để đỡ chiếm chỗ. */}
      {isInstructor && !doing && !results && (
        <div className="card mb-4">
          <div className="flex items-center justify-between">
            <h3 className="text-[12.5px] font-bold">Khái niệm của lớp</h3>
            {concepts.length > 0 && (
              <button
                onClick={() => setShowConceptForm((v) => !v)}
                className="rounded-[7px] border px-2.5 py-1 text-[11.5px] font-semibold"
                style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
              >
                {showConceptForm ? "Đóng" : "+ Thêm khái niệm"}
              </button>
            )}
          </div>
          {concepts.length === 0 && (
            <p className="mb-2 mt-1 text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
              Lớp này chưa có khái niệm nào. Tạo khái niệm trước để hệ thống ra đề.
            </p>
          )}
          {showConceptForm && (
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <div className="min-w-[180px] flex-1">
                <label className="mb-1 block text-[11px] font-semibold" style={{ color: "var(--ink-soft)" }}>
                  Tên khái niệm
                </label>
                <input
                  type="text"
                  value={conceptName}
                  onChange={(e) => setConceptName(e.target.value)}
                  placeholder="vd: Đệ quy"
                  className="w-full rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
                  style={{ borderColor: "var(--border-strong)" }}
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold" style={{ color: "var(--ink-soft)" }}>
                  Độ phức tạp
                </label>
                <select
                  value={conceptComplexity}
                  onChange={(e) => setConceptComplexity(Number(e.target.value))}
                  className="rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
                  style={{ borderColor: "var(--border-strong)" }}
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleCreateConcept}
                disabled={creatingConcept || !conceptName.trim()}
                className="rounded-[7px] px-4 py-2 text-[12.3px] font-semibold text-white disabled:opacity-50"
                style={{ background: "var(--accent)" }}
              >
                {creatingConcept ? "Đang tạo…" : "Tạo khái niệm"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ----- Giảng viên: giao bài mới - BƯỚC 1 (chọn khái niệm + số câu, sinh nháp) ----- */}
      {isInstructor && !doing && !results && !draftQuestions && (
        <div className="card mb-4">
          <h3 className="mb-2 text-[12.5px] font-bold">Giao bài tập mới</h3>
          {concepts.length === 0 ? (
            <p className="text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
              Lớp này chưa có khái niệm nào. Tạo khái niệm trước để hệ thống ra đề.
            </p>
          ) : (
            <>
              <div className="mb-2 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                Chọn khái niệm cần kiểm tra:
              </div>
              <div className="mb-3 flex flex-wrap gap-1.5">
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
              <div className="mb-3 flex items-center gap-2">
                <label className="text-[11.5px] font-semibold" style={{ color: "var(--ink-soft)" }}>
                  Số câu mỗi khái niệm:
                </label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={numPerConcept}
                  onChange={(e) =>
                    setNumPerConcept(Math.min(10, Math.max(1, Number(e.target.value) || 1)))
                  }
                  className="w-16 rounded-[7px] border px-2 py-1.5 text-[12.5px] focus:outline-none"
                  style={{ borderColor: "var(--border-strong)" }}
                />
              </div>
              <button
                onClick={handleGenerate}
                disabled={generating || selectedConcepts.length === 0}
                className="rounded-[7px] px-4 py-2 text-[12.3px] font-semibold text-white disabled:opacity-50"
                style={{ background: "var(--accent)" }}
              >
                {generating
                  ? `Đang sinh ${selectedConcepts.length * numPerConcept} câu hỏi, vui lòng đợi…`
                  : `Sinh câu hỏi (${selectedConcepts.length * numPerConcept} câu)`}
              </button>
            </>
          )}
        </div>
      )}

      {/* ----- Giảng viên: giao bài mới - BƯỚC 2 (xem/sửa/bỏ câu rồi mới giao) ----- */}
      {isInstructor && !doing && !results && draftQuestions && (
        <div className="card mb-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[12.5px] font-bold">Duyệt câu hỏi trước khi giao ({draftQuestions.length} câu)</h3>
            <button
              onClick={handleResetDraft}
              className="rounded-[7px] border px-2.5 py-1 text-[11.5px] font-semibold"
              style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
            >
              Huỷ / Làm lại
            </button>
          </div>

          {draftQuestions.length === 0 && (
            <p className="mb-2 text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
              Bạn đã bỏ hết câu hỏi. Bấm &ldquo;Huỷ / Làm lại&rdquo; để sinh lại từ đầu.
            </p>
          )}

          {draftQuestions.map((q, i) => (
            <div
              key={q.id}
              className="mb-3 rounded-[9px] border px-3 py-2.5 text-[12px]"
              style={{ borderColor: "var(--border-strong)" }}
            >
              {editingId === q.id && editForm ? (
                <div>
                  <div className="mb-1.5 text-[11px] font-semibold" style={{ color: "var(--ink-soft)" }}>
                    Câu {i + 1} · {q.concept_name} · Đang sửa
                  </div>
                  <textarea
                    value={editForm.question}
                    onChange={(e) => setEditForm({ ...editForm, question: e.target.value })}
                    className="mb-2 w-full rounded-[7px] border px-2.5 py-2 text-[12px] focus:outline-none"
                    style={{ borderColor: "var(--border-strong)" }}
                    rows={2}
                  />
                  {editForm.options.map((opt, idx) => (
                    <div key={idx} className="mb-1.5 flex items-center gap-2">
                      <input
                        type="radio"
                        checked={editForm.correct_index === idx}
                        onChange={() => setEditForm({ ...editForm, correct_index: idx })}
                      />
                      <input
                        type="text"
                        value={opt}
                        onChange={(e) => {
                          const options = [...editForm.options];
                          options[idx] = e.target.value;
                          setEditForm({ ...editForm, options });
                        }}
                        className="flex-1 rounded-[7px] border px-2.5 py-1.5 text-[12px] focus:outline-none"
                        style={{
                          borderColor:
                            editForm.correct_index === idx ? "var(--teal)" : "var(--border-strong)",
                        }}
                      />
                    </div>
                  ))}
                  <textarea
                    value={editForm.explanation}
                    onChange={(e) => setEditForm({ ...editForm, explanation: e.target.value })}
                    placeholder="Giải thích đáp án đúng"
                    className="mb-2 w-full rounded-[7px] border px-2.5 py-2 text-[12px] focus:outline-none"
                    style={{ borderColor: "var(--border-strong)" }}
                    rows={2}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleSaveEdit(q.id)}
                      disabled={savingEdit}
                      className="rounded-[7px] px-3 py-1.5 text-[11.5px] font-semibold text-white disabled:opacity-50"
                      style={{ background: "var(--teal)" }}
                    >
                      {savingEdit ? "Đang lưu…" : "Lưu"}
                    </button>
                    <button
                      onClick={() => {
                        setEditingId(null);
                        setEditForm(null);
                      }}
                      className="rounded-[7px] border px-3 py-1.5 text-[11.5px] font-semibold"
                      style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                    >
                      Huỷ sửa
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="mb-1 text-[11px] font-semibold" style={{ color: "var(--ink-soft)" }}>
                    Câu {i + 1} · {q.concept_name}
                  </div>
                  <div className="mb-1.5 font-semibold">{q.question}</div>
                  {q.options.map((opt, idx) => (
                    <div
                      key={idx}
                      className="mb-1 rounded-[7px] px-2.5 py-1.5"
                      style={
                        idx === q.correct_index
                          ? { background: "var(--teal-bg)", color: "var(--teal-ink)", fontWeight: 600 }
                          : { background: "#fff", border: "1px solid var(--border)" }
                      }
                    >
                      {opt}
                      {idx === q.correct_index && " ✓"}
                    </div>
                  ))}
                  {q.explanation && (
                    <div className="mt-1.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                      Giải thích: {q.explanation}
                    </div>
                  )}
                  <div className="mt-2 flex gap-2">
                    <button
                      onClick={() => startEditDraft(q)}
                      className="rounded-[7px] border px-2.5 py-1 text-[11px] font-semibold"
                      style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                    >
                      Sửa
                    </button>
                    <button
                      onClick={() => handleRemoveDraft(q.id)}
                      className="rounded-[7px] border px-2.5 py-1 text-[11px] font-semibold"
                      style={{ borderColor: "var(--red)", color: "var(--red)" }}
                    >
                      Bỏ câu này
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {draftQuestions.length > 0 && (
            <>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Tên bài tập, vd: Kiểm tra giữa kỳ"
                className="mb-2 w-full rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
                style={{ borderColor: "var(--border-strong)" }}
              />
              <button
                onClick={handleAssign}
                disabled={creating || !newTitle.trim()}
                className="rounded-[7px] px-4 py-2 text-[12.3px] font-semibold text-white disabled:opacity-50"
                style={{ background: "var(--accent)" }}
              >
                {creating ? "Đang giao bài…" : `Giao bài (${draftQuestions.length} câu)`}
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
            <div className="visual-empty-state"><span className="visual-empty-state__icon">✓</span><h3>Chưa có bài tập</h3><p>{isInstructor ? "Tạo khái niệm và giao bài đầu tiên bằng công cụ phía trên." : "Giảng viên chưa giao bài cho lớp này. Hãy khám phá tài liệu hoặc hỏi Nova trong lúc chờ nhé."}</p></div>
          )}
          <div className="space-y-2.5">
            {assignments.map((a) => (
              <div key={a.id} className="card assignment-card">
                <div className="flex items-center justify-between gap-3">
                  <span className="assignment-card__visual" aria-hidden="true">✓</span>
                  <div className="min-w-0 flex-1">
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
