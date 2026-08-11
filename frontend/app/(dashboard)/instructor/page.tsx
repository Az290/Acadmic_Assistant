"use client";

import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  CostSummary,
  CoursePublic,
  ClassAnalytics,
  InstructorAnalytics,
  PipelineTiming,
  PopularConcept,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

/**
 * Dashboard giảng viên - thống kê theo lớp.
 *
 * RANH GIỚI QUYỀN RIÊNG TƯ (cập nhật): giảng viên xem được TÊN và tiến
 * độ học tập của từng sinh viên yếu (mục "Sinh viên cần hỗ trợ") - cần
 * thiết để hỗ trợ đúng người, đúng lúc. Nhưng TUYỆT ĐỐI KHÔNG đọc được
 * nội dung câu hỏi, câu trả lời hay lịch sử hội thoại của sinh viên -
 * backend không có endpoint nào trả về dữ liệu đó (xem docstring
 * StudentNeedingSupport trong app/instructor/schemas.py).
 */

const CATEGORY_LABEL: Record<string, string> = {
  RAG_QUESTION: "Hỏi đáp tài liệu",
  SOCRATIC_REQUEST: "Gia sư gợi mở",
  CHITCHAT: "Trò chuyện",
  OFF_TOPIC: "Ngoài phạm vi",
};

const BLOCKED_BY_LABEL: Record<string, string> = {
  rules: "Quy tắc (prompt injection)",
  moderation: "Nội dung không phù hợp",
};

const PIPELINE_STEP_LABEL: Record<string, string> = {
  guardrail_router_ms: "Kiểm duyệt + Phân loại",
  retrieval_ms: "Tìm tài liệu",
  generate_ms: "Sinh câu trả lời",
};

export default function InstructorDashboard() {
  const { user } = useAuth();
  const [courses, setCourses] = useState<CoursePublic[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [analytics, setAnalytics] = useState<InstructorAnalytics | null>(null);
  const [costs, setCosts] = useState<CostSummary | null>(null);
  const [pipeline, setPipeline] = useState<PipelineTiming | null>(null);
  const [popularConcepts, setPopularConcepts] = useState<PopularConcept[]>([]);
  const [classAnalytics, setClassAnalytics] = useState<ClassAnalytics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then((list) => {
        // Chỉ lớp giảng viên này SỞ HỮU mới xem được thống kê (backend
        // cũng chặn, đây là lớp lọc hiển thị cho khớp - tránh hiện lớp
        // rồi bấm vào lại báo lỗi 403).
        const owned = list.filter((c) => c.owner_id === user?.id);
        setCourses(owned);
        if (owned.length > 0) setSelectedCourseId(owned[0].id);
      })
      .catch(() => setCourses([]));
  }, [user?.id]);

  useEffect(() => {
    if (selectedCourseId === null) return;
    setLoading(true);
    setError(null);
    api
      .get<InstructorAnalytics>(`/v1/instructor/analytics?course_id=${selectedCourseId}`)
      .then(setAnalytics)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Không tải được thống kê.")
      )
      .finally(() => setLoading(false));

    api
      .get<CostSummary>(`/v1/instructor/costs?course_id=${selectedCourseId}`)
      .then(setCosts)
      .catch(() => setCosts(null));

    api
      .get<PipelineTiming>(`/v1/instructor/pipeline?course_id=${selectedCourseId}`)
      .then(setPipeline)
      .catch(() => setPipeline(null));

    api
      .get<PopularConcept[]>(`/v1/instructor/popular-concepts?course_id=${selectedCourseId}`)
      .then(setPopularConcepts)
      .catch(() => setPopularConcepts([]));

    api
      .get<ClassAnalytics>(`/v1/instructor/class-analytics?course_id=${selectedCourseId}`)
      .then(setClassAnalytics)
      .catch(() => setClassAnalytics(null));
  }, [selectedCourseId]);

  const insufficientPercent = analytics
    ? Math.round(analytics.insufficient_context.rate * 100)
    : 0;

  return (
    <div className="max-w-5xl">
      <p className="mb-4 text-[13px]" style={{ color: "var(--ink-soft)" }}>
        Thống kê tổng hợp theo lớp — không hiển thị nội dung hội thoại riêng của sinh viên.
      </p>

      {courses.length === 0 && (
        <div className="card">
          <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
            Bạn chưa phụ trách lớp nào. Tạo lớp ở trang &quot;Lớp học&quot; để bắt đầu.
          </p>
        </div>
      )}

      {courses.length > 0 && (
        <>
          <div className="mb-4 flex flex-wrap gap-1.5">
            {courses.map((c) => {
              const active = c.id === selectedCourseId;
              return (
                <button
                  key={c.id}
                  onClick={() => setSelectedCourseId(c.id)}
                  className="rounded-full border px-3 py-1.5 text-xs font-semibold"
                  style={
                    active
                      ? { background: "var(--ink)", color: "#fff", borderColor: "var(--ink)" }
                      : { background: "#fff", borderColor: "var(--border-strong)", color: "var(--ink)" }
                  }
                >
                  {c.code}
                </button>
              );
            })}
          </div>

          {loading && (
            <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
              Đang tải thống kê…
            </p>
          )}

          {error && (
            <p
              className="rounded-[9px] px-3 py-2 text-[13px]"
              style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
            >
              {error}
            </p>
          )}

          {/* Phân tích lớp - đặt ĐẦU TIÊN vì đây là thông tin giảng viên
              cần hành động ngay (ai đang cần giúp), các thống kê vận hành
              phía dưới mang tính tham khảo. */}
          {classAnalytics && !loading && classAnalytics.total_students > 0 && (
            <div className="mb-4">
              <div className="mb-3 grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
                <div className="card">
                  <div className="text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
                    Sinh viên
                  </div>
                  <div className="mt-1.5 font-mono text-[22px] font-extrabold">{classAnalytics.total_students}</div>
                  <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                    {classAnalytics.students_with_data} đã có dữ liệu ·{" "}
                    {classAnalytics.students_without_data} chưa làm quiz
                  </div>
                </div>

                <div className="card">
                  <div className="text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
                    Mastery trung bình
                  </div>
                  <div
                    className="mt-1.5 font-mono text-[22px] font-extrabold"
                    style={{ color: classAnalytics.avg_mastery === null ? "var(--ink-faint)" : "var(--teal)" }}
                  >
                    {classAnalytics.avg_mastery === null
                      ? "—"
                      : `${(classAnalytics.avg_mastery * 100).toFixed(0)}%`}
                  </div>
                  <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                    Chỉ tính sinh viên đã làm quiz
                  </div>
                </div>

                <div className="card">
                  <div className="text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
                    Cần hỗ trợ
                  </div>
                  <div
                    className="mt-1.5 font-mono text-[22px] font-extrabold"
                    style={{ color: classAnalytics.needing_support_count > 0 ? "var(--red)" : "var(--teal)" }}
                  >
                    {classAnalytics.needing_support_count}
                  </div>
                  <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                    Mastery dưới 40%
                  </div>
                </div>
              </div>

              {/* Phân bố mastery - cột dọc, cao theo số sinh viên. Màu
                  theo NGƯỠNG TRÌNH ĐỘ (đỏ yếu → xanh giỏi), không phải
                  theo thứ hạng cột, để đọc được ngay lớp đang lệch về đâu. */}
              {classAnalytics.students_with_data > 0 && (
                <div className="card mb-3">
                  <h3 className="mb-3 text-[12.5px] font-bold">Phân bố mức độ nắm vững</h3>
                  <div className="flex h-[120px] items-end gap-2">
                    {classAnalytics.distribution.map((b, i) => {
                      const maxCount = Math.max(...classAnalytics.distribution.map((x) => x.student_count), 1);
                      const heightPct = (b.student_count / maxCount) * 100;
                      const colors = ["var(--red)", "var(--red)", "var(--amber)", "var(--teal)", "var(--accent)"];
                      return (
                        <div key={b.label} className="flex flex-1 flex-col items-center justify-end">
                          <div className="mb-1 text-[11px] font-bold">{b.student_count}</div>
                          <div
                            className="w-full rounded-t-[4px]"
                            style={{
                              height: `${Math.max(heightPct, b.student_count > 0 ? 6 : 2)}%`,
                              background: b.student_count > 0 ? colors[i] : "#E8EAF0",
                            }}
                          />
                          <div className="mt-1.5 text-[10.5px]" style={{ color: "var(--ink-soft)" }}>
                            {b.label}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {classAnalytics.students_without_data > 0 && (
                    <p className="mt-3 text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
                      {classAnalytics.students_without_data} sinh viên chưa làm quiz nào nên không có trong biểu đồ
                      — chưa có dữ liệu khác hẳn với học kém.
                    </p>
                  )}
                </div>
              )}

              {/* Danh sách sinh viên cần hỗ trợ - CHỈ dữ liệu sư phạm,
                  không có nội dung câu hỏi/hội thoại nào. */}
              {classAnalytics.students_needing_support.length > 0 && (
                <div className="card">
                  <h3 className="mb-2 text-[12.5px] font-bold">Sinh viên cần hỗ trợ</h3>
                  <table className="w-full text-[12.5px]">
                    <thead>
                      <tr style={{ color: "var(--ink-faint)" }}>
                        <th className="py-1.5 text-left text-[10.5px] font-bold uppercase">Sinh viên</th>
                        <th className="py-1.5 text-right text-[10.5px] font-bold uppercase">Mastery</th>
                        <th className="py-1.5 text-left text-[10.5px] font-bold uppercase">Yếu nhất</th>
                        <th className="py-1.5 text-right text-[10.5px] font-bold uppercase">Câu đã hỏi</th>
                      </tr>
                    </thead>
                    <tbody>
                      {classAnalytics.students_needing_support.map((s) => (
                        <tr key={s.user_id} className="border-t" style={{ borderColor: "var(--border)" }}>
                          <td className="py-2">{s.full_name}</td>
                          <td className="py-2 text-right">
                            <span
                              className="rounded-full px-2 py-[2px] font-mono text-[10.5px] font-bold"
                              style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
                            >
                              {(s.mastery * 100).toFixed(0)}%
                            </span>
                          </td>
                          <td className="py-2" style={{ color: "var(--ink-soft)" }}>
                            {s.weakest_concept_name ?? "—"}
                          </td>
                          <td className="py-2 text-right font-mono">{s.question_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {analytics && !loading && (
            <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
              <div className="card">
                <div
                  className="text-[10.5px] font-semibold uppercase tracking-wide"
                  style={{ color: "var(--ink-faint)" }}
                >
                  Tổng lượt hỏi
                </div>
                <div className="mt-1.5 font-mono text-[22px] font-extrabold">
                  {analytics.total_messages}
                </div>
                <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                  Câu trả lời AI đã sinh cho lớp này
                </div>
              </div>

              {/* Widget quan trọng nhất về giá trị sư phạm: điểm mù tài liệu */}
              <div className="card">
                <div
                  className="text-[10.5px] font-semibold uppercase tracking-wide"
                  style={{ color: "var(--ink-faint)" }}
                >
                  Điểm mù tài liệu
                </div>
                <div
                  className="mt-1.5 font-mono text-[22px] font-extrabold"
                  style={{ color: insufficientPercent > 20 ? "var(--red)" : "var(--teal)" }}
                >
                  {insufficientPercent}%
                </div>
                <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                  {analytics.insufficient_context.insufficient_count}/
                  {analytics.insufficient_context.total_rag_questions} câu hỏi không tìm thấy tài liệu
                  phù hợp — cân nhắc bổ sung tài liệu
                </div>
              </div>

              <div className="card">
                <div
                  className="text-[10.5px] font-semibold uppercase tracking-wide"
                  style={{ color: "var(--ink-faint)" }}
                >
                  Cảnh báo liêm chính
                </div>
                <div className="mt-1.5 font-mono text-[22px] font-extrabold">
                  {analytics.security_alerts.reduce((sum, a) => sum + a.count, 0)}
                </div>
                <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                  Lượt bị hệ thống chặn (thống kê, không định danh sinh viên)
                </div>
              </div>

              <div className="card" style={{ gridColumn: "1 / -1" }}>
                <h3 className="mb-2 text-[12.5px] font-bold">Phân loại câu hỏi</h3>
                {analytics.category_breakdown.length === 0 && (
                  <p className="text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
                    Chưa có dữ liệu.
                  </p>
                )}
                {analytics.category_breakdown.map((c) => {
                  const percent =
                    analytics.total_messages > 0
                      ? Math.round((c.count / analytics.total_messages) * 100)
                      : 0;
                  return (
                    <div key={c.category} className="mb-2">
                      <div className="flex justify-between text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                        <span>{CATEGORY_LABEL[c.category] ?? c.category}</span>
                        <span>
                          {c.count} ({percent}%)
                        </span>
                      </div>
                      <div
                        className="mt-1 h-2 overflow-hidden rounded-md"
                        style={{ background: "#E8EAF0" }}
                      >
                        <div
                          className="h-full rounded-md"
                          style={{ width: `${percent}%`, background: "var(--accent)" }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>

              {analytics.security_alerts.length > 0 && (
                <div className="card" style={{ gridColumn: "1 / -1" }}>
                  <h3 className="mb-2 text-[12.5px] font-bold">Chi tiết cảnh báo</h3>
                  {analytics.security_alerts.map((a) => (
                    <div
                      key={a.blocked_by}
                      className="flex justify-between border-b py-1.5 text-[12.5px] last:border-0"
                      style={{ borderColor: "var(--border)" }}
                    >
                      <span style={{ color: "var(--ink-soft)" }}>
                        {BLOCKED_BY_LABEL[a.blocked_by] ?? a.blocked_by}
                      </span>
                      <span className="font-mono font-semibold">{a.count}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Gap Analysis - chủ đề thiếu tài liệu nhất lên đầu */}
              {analytics.concept_gaps.length > 0 && (
                <div className="card" style={{ gridColumn: "1 / -1" }}>
                  <h3 className="mb-2 text-[12.5px] font-bold">Chủ đề thiếu tài liệu (Gap Analysis)</h3>
                  {analytics.concept_gaps.map((g) => {
                    const percent = Math.round(g.gap_rate * 100);
                    return (
                      <div key={g.concept_id ?? "unclassified"} className="mb-2">
                        <div className="flex justify-between text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                          <span>{g.concept_name}</span>
                          <span>
                            {g.unanswered_questions}/{g.total_questions} câu không trả lời được ({percent}%)
                          </span>
                        </div>
                        <div className="mt-1 h-2 overflow-hidden rounded-md" style={{ background: "#E8EAF0" }}>
                          <div
                            className="h-full rounded-md"
                            style={{
                              width: `${percent}%`,
                              background: percent > 0 ? "var(--red)" : "var(--teal)",
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Câu hỏi phổ biến - gom theo KHÁI NIỆM, không phải câu
                  hỏi thô (sinh viên diễn đạt cùng 1 thắc mắc bằng vô số
                  cách khác nhau). Không hiện nội dung câu hỏi của bất kỳ
                  sinh viên nào - giữ đúng ranh giới riêng tư. */}
              {popularConcepts.length > 0 && (
                <div className="card" style={{ gridColumn: "1 / -1" }}>
                  <h3 className="mb-2 text-[12.5px] font-bold">Khái niệm được hỏi nhiều nhất</h3>
                  <table className="w-full text-[12px]">
                    <thead>
                      <tr style={{ color: "var(--ink-faint)" }}>
                        <th className="py-1.5 text-left text-[10.5px] font-bold uppercase">Khái niệm</th>
                        <th className="py-1.5 text-right text-[10.5px] font-bold uppercase">Lần hỏi</th>
                        <th className="py-1.5 text-right text-[10.5px] font-bold uppercase">Độ khớp TL</th>
                        <th className="py-1.5 text-right text-[10.5px] font-bold uppercase">Phản hồi SV</th>
                      </tr>
                    </thead>
                    <tbody>
                      {popularConcepts.map((c) => (
                        <tr key={c.concept_id} className="border-t" style={{ borderColor: "var(--border)" }}>
                          <td className="py-2">
                            {c.concept_name}
                            {c.needs_attention && (
                              <span
                                className="ml-2 rounded-full px-2 py-[2px] text-[9.5px] font-bold"
                                style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
                              >
                                Cần bổ sung tài liệu
                              </span>
                            )}
                          </td>
                          <td className="py-2 text-right font-mono">{c.question_count}</td>
                          <td className="py-2 text-right">
                            {c.avg_retrieval_similarity === null ? (
                              <span style={{ color: "var(--ink-faint)" }}>—</span>
                            ) : (
                              <span
                                className="font-mono"
                                style={{
                                  color:
                                    c.avg_retrieval_similarity < 0.5 ? "var(--red-ink)" : "var(--ink-soft)",
                                }}
                                title="Mức tương đồng của tài liệu tìm được với câu hỏi. KHÔNG phải xác suất câu trả lời đúng."
                              >
                                {(c.avg_retrieval_similarity * 100).toFixed(0)}%
                              </span>
                            )}
                          </td>
                          <td className="py-2 text-right">
                            {/* positive_rate = null nghĩa là chưa đủ phiếu
                                để kết luận - KHÁC 0% (đã có phiếu, toàn
                                tiêu cực). Không được hiển thị lẫn lộn. */}
                            {c.positive_rate === null ? (
                              <span
                                style={{ color: "var(--ink-faint)" }}
                                title={`Mới có ${c.feedback_count} lượt đánh giá - chưa đủ để kết luận`}
                              >
                                Chưa đủ dữ liệu
                              </span>
                            ) : (
                              <span
                                className="font-mono"
                                style={{
                                  color: c.positive_rate < 0.6 ? "var(--red-ink)" : "var(--teal-ink)",
                                }}
                                title={`${c.feedback_count} lượt đánh giá`}
                              >
                                {(c.positive_rate * 100).toFixed(0)}% hài lòng
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {popularConcepts.some((c) => c.needs_attention) && (
                    <p
                      className="mt-3 rounded-[9px] border px-3 py-2 text-[12px]"
                      style={{ background: "var(--amber-bg)", borderColor: "#F0D589", color: "var(--amber-ink)" }}
                    >
                      Các khái niệm đánh dấu <strong>&quot;Cần bổ sung tài liệu&quot;</strong> có nhiều lượt hỏi
                      nhưng hệ thống tìm được tài liệu ít liên quan và sinh viên phản hồi chưa hài lòng — cân nhắc
                      tải thêm tài liệu về những chủ đề này.
                    </p>
                  )}
                </div>
              )}

              {/* Cost Dashboard */}
              {costs && costs.total_messages_measured > 0 && (
                <>
                  <div className="card">
                    <div
                      className="text-[10.5px] font-semibold uppercase tracking-wide"
                      style={{ color: "var(--ink-faint)" }}
                    >
                      Chi phí đã phát sinh
                    </div>
                    <div className="mt-1.5 font-mono text-[22px] font-extrabold">
                      ${costs.total_cost_usd.toFixed(4)}
                    </div>
                    <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                      {costs.total_messages_measured} câu · trung bình ${costs.avg_cost_per_message_usd.toFixed(6)}/câu
                    </div>
                  </div>

                  <div className="card">
                    <div
                      className="text-[10.5px] font-semibold uppercase tracking-wide"
                      style={{ color: "var(--ink-faint)" }}
                    >
                      Dự báo/tháng (100 SV)
                    </div>
                    <div className="mt-1.5 font-mono text-[22px] font-extrabold">
                      ${costs.projected_monthly_usd_per_100_students.toFixed(2)}
                    </div>
                    <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                      Ước lượng thô, ngoại suy tuyến tính từ mức dùng hiện tại
                    </div>
                  </div>
                </>
              )}

              {/* Pipeline Visualization */}
              {pipeline && pipeline.total_messages_measured > 0 && (
                <div className="card" style={{ gridColumn: "1 / -1" }}>
                  <h3 className="mb-2 text-[12.5px] font-bold">
                    Thời gian xử lý từng bước (trung bình {pipeline.avg_total_ms.toFixed(0)}ms/câu)
                  </h3>
                  {pipeline.steps.map((s) => {
                    const percent = pipeline.avg_total_ms > 0 ? Math.round((s.avg_ms / pipeline.avg_total_ms) * 100) : 0;
                    return (
                      <div key={s.step} className="mb-2">
                        <div className="flex justify-between text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                          <span>{PIPELINE_STEP_LABEL[s.step] ?? s.step}</span>
                          <span>
                            {s.avg_ms.toFixed(0)}ms (p95: {s.p95_ms.toFixed(0)}ms)
                          </span>
                        </div>
                        <div className="mt-1 h-2 overflow-hidden rounded-md" style={{ background: "#E8EAF0" }}>
                          <div
                            className="h-full rounded-md"
                            style={{ width: `${percent}%`, background: "var(--blue)" }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
