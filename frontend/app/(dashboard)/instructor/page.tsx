"use client";

import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  CostSummary,
  CoursePublic,
  InstructorAnalytics,
  PipelineTiming,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

/**
 * Dashboard giảng viên - thống kê TỔNG HỢP theo lớp, KHÔNG cá nhân hoá.
 *
 * Nguyên tắc quyền riêng tư (đã chốt từ đầu dự án): giảng viên KHÔNG
 * đọc được nội dung hội thoại của từng sinh viên - backend cũng không
 * có endpoint nào trả về dữ liệu đó (xem app/instructor/router.py).
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
