"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, CoursePublic, StudentRosterItem } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

export default function CoursesPage() {
  const { user } = useAuth();
  const router = useRouter();
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

  // Bảng roster (danh sách sinh viên) - hiển thị/ẩn theo course đang
  // chọn, giống cơ chế mở/đóng của form "+ Thêm học sinh" ở trên.
  const [viewingRosterCourseId, setViewingRosterCourseId] = useState<number | null>(null);
  const [roster, setRoster] = useState<StudentRosterItem[]>([]);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [rosterError, setRosterError] = useState<string | null>(null);
  // user_id đang bị xoá - dùng để disable đúng nút "Gỡ khỏi lớp" đang bấm,
  // tránh double-click gửi 2 request xoá cùng lúc.
  const [removingStudentId, setRemovingStudentId] = useState<number | null>(null);

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
      // Nếu roster của đúng lớp này đang mở, refresh luôn để thấy ngay
      // sinh viên vừa thêm mà không cần đóng/mở lại bảng.
      if (viewingRosterCourseId === courseId) {
        await loadRoster(courseId);
      }
    } catch (err) {
      setEnrollError(err instanceof ApiError ? err.detail : "Không thể thêm học sinh.");
    }
  }

  async function loadRoster(courseId: number) {
    setRosterLoading(true);
    setRosterError(null);
    try {
      const list = await api.get<StudentRosterItem[]>(`/v1/courses/${courseId}/students`);
      setRoster(list);
    } catch (err) {
      setRosterError(err instanceof ApiError ? err.detail : "Không thể tải danh sách sinh viên.");
      setRoster([]);
    } finally {
      setRosterLoading(false);
    }
  }

  function toggleRoster(courseId: number) {
    if (viewingRosterCourseId === courseId) {
      setViewingRosterCourseId(null);
      return;
    }
    setViewingRosterCourseId(courseId);
    loadRoster(courseId);
  }

  async function handleRemoveStudent(courseId: number, studentUserId: number, studentName: string) {
    const confirmed = window.confirm(`Gỡ ${studentName} khỏi lớp? Hành động này không thể hoàn tác.`);
    if (!confirmed) return;

    setRemovingStudentId(studentUserId);
    setRosterError(null);
    try {
      await api.delete(`/v1/courses/${courseId}/students/${studentUserId}`);
      // Gọi lại API để lấy danh sách THẬT từ server thay vì tự suy luận
      // xoá khỏi state - tránh lệch dữ liệu nếu có thay đổi khác xen vào.
      await loadRoster(courseId);
    } catch (err) {
      setRosterError(err instanceof ApiError ? err.detail : "Không thể gỡ sinh viên khỏi lớp.");
    } finally {
      setRemovingStudentId(null);
    }
  }

  /** Format ngày tham gia lớp - chỉ cần ngày cụ thể, không cần "x ngày trước". */
  function formatEnrolledDate(iso: string): string {
    return new Date(iso).toLocaleDateString("vi-VN");
  }

  return (
    <div className="courses-page max-w-3xl">
      <section className="page-visual-hero page-visual-hero--courses">
        <div>
          <span className="page-visual-hero__eyebrow">Không gian học tập</span>
          <h2>{canManage ? "Quản lý lớp học của bạn" : "Các lớp bạn đang tham gia"}</h2>
          <p>
            {canManage
              ? "Tạo lớp, quản lý sinh viên và kết nối tài liệu với từng môn học."
              : "Mỗi lớp là một không gian riêng cho bài tập, tài liệu và trợ lý Nova."}
          </p>
        </div>
        <div className="page-visual-hero__metric"><strong>{courses.length}</strong><span>Lớp học</span></div>
        <div className="hero-orbit" aria-hidden="true"><span>⌘</span><span>✦</span><span>●</span></div>
      </section>
      {canManage && (
        <form onSubmit={handleCreateCourse} className="card create-course-card mb-4">
          <div className="section-heading-row">
            <span className="section-heading-icon">＋</span>
            <div><h2>Tạo lớp mới</h2><p>Mở một không gian học tập và bắt đầu thêm sinh viên.</p></div>
          </div>
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
        <div className="visual-empty-state">
          <span className="visual-empty-state__icon">▱</span>
          <h3>Chưa có lớp học</h3>
          <p>{canManage ? "Tạo lớp đầu tiên bằng biểu mẫu phía trên." : "Liên hệ giảng viên để được thêm vào lớp."}</p>
        </div>
      )}

      <div className="courses-grid">
        {courses.map((c, index) => (
          <div key={c.id} className={`card course-card course-card--${index % 3} ${viewingRosterCourseId === c.id ? "course-card--expanded" : ""}`}>
            <div className="flex items-center justify-between">
              <div className="course-card__identity">
                <span className="course-card__visual" aria-hidden="true">{c.code.slice(0, 2)}</span>
                <div>
                  <span className="course-card__code">{c.code}</span>
                  <div className="course-card__name">{c.name}</div>
                  <div className="course-card__meta">Không gian môn học · Nova sẵn sàng</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => router.push(`/courses/${c.id}`)}
                  className="rounded-[7px] px-3.5 py-1.5 text-[12.3px] font-semibold text-white"
                  style={{ background: "var(--accent)" }}
                >
                  Vào lớp
                </button>
              {canManage && c.owner_id === user?.id && (
                <div className="flex gap-2">
                  <button
                    onClick={() => toggleRoster(c.id)}
                    className="rounded-[7px] border px-3 py-1.5 text-[12.3px] font-semibold hover:bg-[#F0F2F8]"
                    style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                  >
                    {viewingRosterCourseId === c.id ? "Ẩn danh sách" : "Xem danh sách"}
                  </button>
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
                </div>
              )}
              </div>
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

            {viewingRosterCourseId === c.id && (
              <div className="mt-3 border-t pt-3" style={{ borderColor: "var(--border)" }}>
                {rosterLoading && (
                  <p className="text-[12.5px]" style={{ color: "var(--ink-faint)" }}>Đang tải danh sách…</p>
                )}
                {!rosterLoading && rosterError && (
                  <p className="rounded-[9px] px-3 py-2 text-[12px]" style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}>
                    {rosterError}
                  </p>
                )}
                {!rosterLoading && !rosterError && roster.length === 0 && (
                  <p className="text-[12.5px]" style={{ color: "var(--ink-faint)" }}>Lớp chưa có sinh viên nào.</p>
                )}
                {!rosterLoading && !rosterError && roster.length > 0 && (
                  <table className="w-full text-[12px]">
                    <thead>
                      <tr style={{ color: "var(--ink-faint)" }}>
                        <th className="pb-1.5 text-left font-medium">Tên</th>
                        <th className="pb-1.5 text-left font-medium">Email</th>
                        <th className="pb-1.5 text-left font-medium">Ngày tham gia</th>
                        <th className="pb-1.5"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {roster.map((s) => (
                        <tr key={s.user_id} className="border-t" style={{ borderColor: "var(--border)" }}>
                          <td className="py-1.5 pr-2">{s.full_name}</td>
                          <td className="py-1.5 pr-2" style={{ color: "var(--ink-soft)" }}>{s.email}</td>
                          <td className="py-1.5 pr-2" style={{ color: "var(--ink-soft)" }}>{formatEnrolledDate(s.enrolled_at)}</td>
                          <td className="py-1.5 text-right">
                            <button
                              onClick={() => handleRemoveStudent(c.id, s.user_id, s.full_name)}
                              disabled={removingStudentId === s.user_id}
                              className="rounded-[6px] px-2 py-1 text-[11.5px] font-semibold disabled:opacity-60"
                              style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
                            >
                              {removingStudentId === s.user_id ? "Đang gỡ…" : "Gỡ khỏi lớp"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
