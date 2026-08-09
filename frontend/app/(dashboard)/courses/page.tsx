"use client";

import { useState, useEffect } from "react";
import { api, ApiError, CoursePublic } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

export default function CoursesPage() {
  const { user } = useAuth();
  const [courses, setCourses] = useState<CoursePublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form tạo lớp - chỉ INSTRUCTOR/ADMIN dùng tới, nhưng vẫn khai báo
  // state ở đây (không tách component riêng) vì trang này còn nhỏ,
  // chưa cần tách - dễ đọc hơn khi tách khi trang phình to hơn sau này.
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Form thêm học sinh - hiển thị theo course đang chọn
  const [enrollingCourseId, setEnrollingCourseId] = useState<number | null>(null);
  const [studentEmail, setStudentEmail] = useState("");
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [enrollSuccess, setEnrollSuccess] = useState<string | null>(null);

  const canManage = user?.role === "INSTRUCTOR" || user?.role === "ADMIN";

  async function loadCourses() {
    setLoading(true);
    try {
      const list = await api.get<CoursePublic[]>("/v1/courses/me");
      setCourses(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không thể tải danh sách lớp.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCourses();
  }, []);

  async function handleCreateCourse(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      await api.post("/v1/courses", { code, name });
      setCode("");
      setName("");
      await loadCourses();
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.detail : "Không thể tạo lớp.");
    } finally {
      setCreating(false);
    }
  }

  async function handleEnroll(courseId: number, e: React.FormEvent) {
    e.preventDefault();
    setEnrollError(null);
    setEnrollSuccess(null);
    try {
      await api.post(`/v1/courses/${courseId}/enroll`, { student_email: studentEmail });
      setEnrollSuccess(`Đã thêm ${studentEmail} vào lớp.`);
      setStudentEmail("");
    } catch (err) {
      setEnrollError(err instanceof ApiError ? err.detail : "Không thể thêm học sinh.");
    }
  }

  return (
    <div className="max-w-3xl">
      {canManage && (
        <form onSubmit={handleCreateCourse} className="card mb-4">
          <h2 className="mb-2.5 text-[12.5px] font-bold">Tạo lớp mới</h2>
          <div className="flex gap-2">
            <input
              type="text"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Mã lớp, vd: CS301-T7"
              className="w-40 rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
              style={{ borderColor: "var(--border-strong)" }}
            />
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Tên lớp"
              className="flex-1 rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
              style={{ borderColor: "var(--border-strong)" }}
            />
            <button
              type="submit"
              disabled={creating}
              className="rounded-[7px] px-4 py-2 text-[12.3px] font-semibold text-white disabled:opacity-60"
              style={{ background: "var(--accent)" }}
            >
              Tạo
            </button>
          </div>
          {createError && (
            <p className="mt-2 rounded-[9px] px-3 py-2 text-[12.5px]" style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}>
              {createError}
            </p>
          )}
        </form>
      )}

      {loading && <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>Đang tải…</p>}
      {error && (
        <p className="rounded-[9px] px-3 py-2 text-[13px]" style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}>
          {error}
        </p>
      )}

      {!loading && courses.length === 0 && (
        <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>Bạn chưa thuộc lớp nào.</p>
      )}

      <div className="space-y-2.5">
        {courses.map((c) => (
          <div key={c.id} className="card">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[13px] font-semibold">{c.name}</div>
                <div className="text-[11.5px]" style={{ color: "var(--ink-soft)" }}>{c.code}</div>
              </div>
              {canManage && c.owner_id === user?.id && (
                <button
                  onClick={() => {
                    setEnrollingCourseId(enrollingCourseId === c.id ? null : c.id);
                    setEnrollError(null);
                    setEnrollSuccess(null);
                  }}
                  className="rounded-[7px] border px-3 py-1.5 text-[12.3px] font-semibold hover:bg-[#F0F2F8]"
                  style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                >
                  + Thêm học sinh
                </button>
              )}
            </div>

            {enrollingCourseId === c.id && (
              <form
                onSubmit={(e) => handleEnroll(c.id, e)}
                className="mt-3 flex gap-2 border-t pt-3"
                style={{ borderColor: "var(--border)" }}
              >
                <input
                  type="email"
                  required
                  value={studentEmail}
                  onChange={(e) => setStudentEmail(e.target.value)}
                  placeholder="Email học sinh"
                  className="flex-1 rounded-[7px] border px-2.5 py-1.5 text-[12.5px] focus:outline-none"
                  style={{ borderColor: "var(--border-strong)" }}
                />
                <button
                  type="submit"
                  className="rounded-[7px] px-3 py-1.5 text-[12.3px] font-semibold text-white"
                  style={{ background: "var(--accent)" }}
                >
                  Thêm
                </button>
              </form>
            )}
            {enrollingCourseId === c.id && enrollError && (
              <p className="mt-2 text-[11.5px]" style={{ color: "var(--red-ink)" }}>{enrollError}</p>
            )}
            {enrollingCourseId === c.id && enrollSuccess && (
              <p className="mt-2 text-[11.5px]" style={{ color: "var(--teal-ink)" }}>{enrollSuccess}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
