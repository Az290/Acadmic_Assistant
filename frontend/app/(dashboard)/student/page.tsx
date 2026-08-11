"use client";

import { useEffect, useState } from "react";
import { api, CoursePublic } from "@/lib/api";
import WeakestConceptToast from "@/components/WeakestConceptToast";

interface MasteryPublic {
  concept_id: number;
  concept_name: string;
  streak: number;
  n_obs: number;
  n_correct: number;
  mastered: boolean;
}

/**
 * Dashboard sinh viên - lớp đang học + tiến độ nắm vững từng khái niệm
 * (dữ liệu từ Learning Assistant, xem app/learning/ ở backend).
 */
export default function StudentDashboard() {
  const [courses, setCourses] = useState<CoursePublic[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [mastery, setMastery] = useState<MasteryPublic[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then((list) => {
        setCourses(list);
        if (list.length > 0) setSelectedCourseId(list[0].id);
      })
      .catch(() => setCourses([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedCourseId === null) return;
    api
      .get<MasteryPublic[]>(`/v1/learn/mastery?course_id=${selectedCourseId}`)
      .then(setMastery)
      .catch(() => setMastery([]));
  }, [selectedCourseId]);

  const masteredCount = mastery.filter((m) => m.mastered).length;

  return (
    <div className="max-w-4xl">
      <WeakestConceptToast />

      <p className="mb-4 text-[13px]" style={{ color: "var(--ink-soft)" }}>
        Bấm biểu tượng chat ở góc phải dưới để hỏi bài bất cứ lúc nào.
      </p>

      {loading && (
        <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
          Đang tải…
        </p>
      )}

      {!loading && courses.length === 0 && (
        <div className="card">
          <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
            Bạn chưa thuộc lớp nào. Liên hệ giảng viên để được thêm vào lớp.
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

          <div className="card mb-3">
            <div
              className="text-[10.5px] font-semibold uppercase tracking-wide"
              style={{ color: "var(--ink-faint)" }}
            >
              Khái niệm đã nắm vững
            </div>
            <div className="mt-1.5 font-mono text-[22px] font-extrabold">
              {masteredCount}/{mastery.length}
            </div>
          </div>

          <div className="card">
            <h3 className="mb-2 text-[12.5px] font-bold">Tiến độ học tập</h3>
            {mastery.length === 0 && (
              <p className="text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
                Lớp này chưa có khái niệm nào được giảng viên tạo.
              </p>
            )}
            {mastery.map((m) => {
              const accuracy = m.n_obs > 0 ? Math.round((m.n_correct / m.n_obs) * 100) : 0;
              return (
                <div
                  key={m.concept_id}
                  className="flex items-center justify-between border-b py-2 last:border-0"
                  style={{ borderColor: "var(--border)" }}
                >
                  <div>
                    <div className="text-[13px] font-semibold">{m.concept_name}</div>
                    <div className="text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                      {m.n_obs > 0
                        ? `${m.n_correct}/${m.n_obs} đúng (${accuracy}%) · chuỗi hiện tại: ${m.streak}`
                        : "Chưa làm quiz nào"}
                    </div>
                  </div>
                  <span
                    className="rounded-full px-2.5 py-[3px] text-[10.5px] font-bold"
                    style={
                      m.mastered
                        ? { background: "var(--teal-bg)", color: "var(--teal-ink)" }
                        : { background: "#E8EAF0", color: "var(--ink-soft)" }
                    }
                  >
                    {m.mastered ? "Đã nắm vững" : "Đang học"}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
