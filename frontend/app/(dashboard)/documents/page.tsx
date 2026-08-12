"use client";

import { useState, useEffect } from "react";
import { api, ApiError, CoursePublic, DocumentPublic } from "@/lib/api";

export default function DocumentsPage() {
  const [courses, setCourses] = useState<CoursePublic[]>([]);
  const [courseId, setCourseId] = useState<number | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<DocumentPublic[]>([]);
  // Quyền truy cập nội dung sau khi tài liệu được duyệt - backend là
  // nơi chặn thật (app/retrieval/access_policy.py), ô chọn này chỉ là
  // giao diện. Mặc định COURSE: mọi người trong lớp đọc được.
  const [visibility, setVisibility] = useState<"COURSE" | "INSTRUCTOR_ONLY">("COURSE");

  useEffect(() => {
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then(setCourses)
      .catch(() => setCourses([]));
  }, []);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file || courseId === "") return;

    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const doc = await api.postForm<DocumentPublic>(
        `/v1/documents/upload?course_id=${courseId}&visibility=${visibility}`,
        formData
      );
      setUploaded((prev) => [doc, ...prev]);
      setFile(null);
      (document.getElementById("fileInput") as HTMLInputElement | null)?.value &&
        ((document.getElementById("fileInput") as HTMLInputElement).value = "");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không thể tải tài liệu lên.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <p className="mb-4 text-[13px]" style={{ color: "var(--ink-soft)" }}>
        Tải lên file PDF — hệ thống tự động phân tích và đưa vào kho tra cứu cho sinh viên.
      </p>

      <form onSubmit={handleUpload} className="card space-y-4">
        <div>
          <label className="mb-1 block text-[11.5px] font-semibold" style={{ color: "var(--ink-soft)" }}>
            Lớp học
          </label>
          <select
            required
            value={courseId}
            onChange={(e) => setCourseId(e.target.value ? Number(e.target.value) : "")}
            className="w-full rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
            style={{ borderColor: "var(--border-strong)" }}
          >
            <option value="">— Chọn lớp —</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.code})
              </option>
            ))}
          </select>
          {courses.length === 0 && (
            <p className="mt-1 text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
              Bạn chưa sở hữu lớp nào — tạo lớp trước ở trang &quot;Lớp học&quot;.
            </p>
          )}
        </div>

        <div>
          <label className="mb-1 block text-[11.5px] font-semibold" style={{ color: "var(--ink-soft)" }}>
            File PDF (tối đa 50MB)
          </label>
          <input
            id="fileInput"
            type="file"
            required
            accept=".pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="w-full rounded-[7px] border px-2.5 py-2 text-[12.5px] file:mr-3 file:rounded file:border-0 file:bg-[#E8EAF0] file:px-3 file:py-1 file:text-[12.5px]"
            style={{ borderColor: "var(--border-strong)" }}
          />
        </div>

        <div>
          <label className="mb-1 block text-[11.5px] font-semibold" style={{ color: "var(--ink-soft)" }}>
            Quyền truy cập
          </label>
          <select
            value={visibility}
            onChange={(e) => setVisibility(e.target.value as "COURSE" | "INSTRUCTOR_ONLY")}
            className="w-full rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
            style={{ borderColor: "var(--border-strong)" }}
          >
            <option value="COURSE">Sinh viên trong lớp tra cứu được</option>
            <option value="INSTRUCTOR_ONLY">Chỉ giảng viên (đề thi, đáp án…)</option>
          </select>
          {visibility === "INSTRUCTOR_ONLY" && (
            <p className="mt-1 text-[11.5px]" style={{ color: "var(--amber-ink)" }}>
              Sinh viên sẽ không tra cứu được nội dung này, kể cả khi hỏi trợ lý AI.
            </p>
          )}
        </div>

        {error && (
          <p className="rounded-[9px] px-3 py-2 text-[12.5px]" style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={uploading || !file || courseId === ""}
          className="rounded-[7px] px-5 py-2 text-[12.3px] font-semibold text-white disabled:opacity-50"
          style={{ background: "var(--accent)" }}
        >
          {uploading ? "Đang xử lý…" : "Tải lên"}
        </button>
      </form>

      {uploaded.length > 0 && (
        <div className="mt-5">
          <h2 className="mb-2 text-[12.5px] font-bold">Đã tải lên phiên này</h2>
          <div className="space-y-2">
            {uploaded.map((d) => (
              <div key={d.id} className="card py-2.5">
                <div className="text-[13px] font-semibold">{d.title}</div>
                <div className="text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                  Trạng thái: {d.status} · {d.image_count} ảnh chưa xử lý
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="mt-5 text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
        Ghi chú: hệ thống hiện chưa có trang xem lại toàn bộ lịch sử tài liệu đã tải lên (backend chưa
        có endpoint liệt kê) — chỉ hiển thị các tài liệu vừa tải lên trong phiên làm việc này.
      </p>
    </div>
  );
}
