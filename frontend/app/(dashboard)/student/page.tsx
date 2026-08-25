"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, CoursePublic, MasteryOverview } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import NovaAvatar from "@/components/NovaAvatar";
import WeakestConceptToast from "@/components/WeakestConceptToast";
import LearningPathCard from "@/components/learning-path/LearningPathCard";

/**
 * Trang chủ sinh viên - trả lời đúng 1 câu hỏi: "hôm nay tôi làm gì
 * tiếp theo?".
 *
 * Chi tiết tiến độ nằm ở trang riêng /mastery; ở đây chỉ hiện con số
 * tổng để sinh viên biết mình đang ở đâu, rồi dẫn tới hành động.
 *
 * Proactive Toast giữ NGUYÊN hành vi (components/WeakestConceptToast.tsx).
 */
export default function StudentDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [courses, setCourses] = useState<CoursePublic[]>([]);
  const [mastery, setMastery] = useState<MasteryOverview | null>(null);
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<CoursePublic[]>("/v1/courses/me").catch(() => [] as CoursePublic[]),
      api.get<MasteryOverview>("/v1/learn/mastery/overview").catch(() => null),
    ])
      .then(([c, m]) => {
        setCourses(c);
        setMastery(m);
        // Auto-select first course if available
        if (c.length > 0 && !selectedCourseId) {
          setSelectedCourseId(c[0].id);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  // Update selected course when courses load
  useEffect(() => {
    if (courses.length > 0 && !selectedCourseId) {
      setSelectedCourseId(courses[0].id);
    }
  }, [courses, selectedCourseId]);

  /** Mở khung chat ở đúng tab - tái dùng CustomEvent đã có (ChatBubble
   *  nằm trong layout dùng chung nên không truyền props trực tiếp được). */
  function openChat(tab: "RAG_QUESTION" | "SOCRATIC_REQUEST") {
    window.dispatchEvent(new CustomEvent("open-chat-tab", { detail: { tab } }));
  }

  const firstName = user?.full_name?.trim().split(/\s+/).slice(-1)[0] ?? "bạn";
  const weakest = mastery?.weak_concepts?.[0];

  return (
    <div className="animate-enter max-w-3xl">
      <WeakestConceptToast />

      {/* Khối chào - nền tối làm mỏ neo thị giác cho cả trang, đồng thời
          là nơi duy nhất Nova tự giới thiệu sự hiện diện. */}
      <section className="rounded-[12px] px-6 py-5" style={{ background: "var(--sidebar)" }}>
        <div className="flex items-start gap-3">
          <NovaAvatar size={34} />
          <div className="min-w-0 flex-1">
            <h2 className="text-[17px] font-semibold text-white">Chào {firstName}</h2>
            <p className="mt-1 text-[13px] leading-relaxed" style={{ color: "var(--sidebar-ink)" }}>
              {loading
                ? "Đang tải…"
                : courses.length === 0
                  ? "Bạn chưa thuộc lớp nào — liên hệ giảng viên để được thêm vào lớp."
                  : weakest
                    ? `Mình là Nova. Hôm nay bạn có thể ôn lại "${weakest.concept_name}" — phần đang yếu nhất.`
                    : "Mình là Nova, hỏi mình bất cứ điều gì về nội dung môn học."}
            </p>
          </div>
        </div>
      </section>

      {/* Số liệu tổng - chỉ 3 con số, đủ để định vị bản thân mà không
          biến trang chủ thành bảng thống kê. */}
      {!loading && mastery && mastery.overall_mastery !== null && (
        <div className="mt-4 grid grid-cols-3 gap-3">
          <StatTile label="Mức nắm vững" value={`${Math.round(mastery.overall_mastery * 100)}%`} />
          <StatTile label="Lớp đang học" value={String(courses.length)} />
          <StatTile label="Cần ôn lại" value={String(mastery.weak_concepts.length)} />
        </div>
      )}

      {/* Learning Path Section */}
      {!loading && selectedCourseId && (
        <section className="mt-6">
          {/* Course Selector */}
          {courses.length > 1 && (
            <div className="mb-3 flex items-center gap-2">
              <span className="text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                Xem lộ trình:
              </span>
              <select
                value={selectedCourseId}
                onChange={(e) => setSelectedCourseId(Number(e.target.value))}
                className="rounded-[6px] border px-2 py-1 text-[12px]"
                style={{
                  borderColor: "var(--border)",
                  background: "var(--bg-raised)",
                  color: "var(--ink)",
                }}
              >
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.code} - {course.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <LearningPathCard
            courseId={selectedCourseId}
            onConceptClick={(conceptId) => {
              // Navigate to quiz page with the concept selected
              router.push(`/quiz?concept_id=${conceptId}`);
            }}
          />
        </section>
      )}

      <h3 className="text-label mt-6 mb-2.5">Bắt đầu từ đâu</h3>
      <div className="space-y-2">
        <ActionRow
          title="Hỏi đáp học thuật"
          description="Đặt câu hỏi bất kỳ — Nova trả lời dựa trên tài liệu đã được giảng viên duyệt, kèm trích dẫn để bạn tự kiểm chứng."
          onClick={() => openChat("RAG_QUESTION")}
        />
        <ActionRow
          title="Gia sư Socratic"
          description="Nova gợi mở từng bước để bạn tự tìm ra đáp án, thay vì đưa lời giải ngay."
          onClick={() => openChat("SOCRATIC_REQUEST")}
        />
        <ActionRow
          title="Tiến độ học tập"
          description="Xem bạn đã nắm vững phần nào, phần nào cần ôn lại, và làm quiz ôn tập."
          onClick={() => router.push("/mastery")}
        />
        <ActionRow
          title="Lịch sử hỏi đáp"
          description="Xem lại các câu đã hỏi và nguồn tài liệu Nova đã dùng để trả lời."
          onClick={() => router.push("/history")}
        />
      </div>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <div className="text-label">{label}</div>
      <div className="text-metric mt-1">{value}</div>
    </div>
  );
}

/**
 * Hàng hành động - dùng đường kẻ ngang + phân cấp chữ thay vì icon
 * trang trí, tránh cảm giác "mỗi dòng một biểu tượng" gây rối mắt.
 * Mũi tên chỉ hiện khi rê chuột: gợi ý bấm được mà không ồn ào.
 */
function ActionRow({
  title,
  description,
  onClick,
}: {
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button onClick={onClick} className="card-interactive group block w-full text-left">
      <div className="flex items-center justify-between gap-3">
        <span className="text-section-title">{title}</span>
        <span
          className="text-[15px] opacity-0 transition-opacity group-hover:opacity-100"
          style={{ color: "var(--accent-strong)", transitionDuration: "var(--motion-fast)" }}
          aria-hidden="true"
        >
          →
        </span>
      </div>
      <p className="text-support mt-1">{description}</p>
    </button>
  );
}
