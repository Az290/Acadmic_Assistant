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
      const fileInput = document.getElementById("fileInput") as HTMLInputElement | null;
      if (fileInput) fileInput.value = "";
      // Tài liệu vừa tải lên còn ở trạng thái PENDING_REVIEW, CHƯA hiện
      // trong danh sách "đã duyệt" bên dưới ngay lập tức - không cần
      // refresh danh sách ở đây, nó chỉ đổi sau khi giảng viên duyệt.
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không thể tải tài liệu lên.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="documents-page max-w-3xl">
      <section className="page-visual-hero page-visual-hero--documents">
        <div><span className="page-visual-hero__eyebrow">Kho tri thức</span><h2>Biến tài liệu thành kiến thức có thể hỏi</h2><p>Nova tự động đọc, chia nhỏ và lập chỉ mục PDF để hỗ trợ học tập có trích dẫn.</p></div>
        <div className="document-stack-visual" aria-hidden="true"><span>PDF</span><i></i><i></i></div>
      </section>

      <div className="documents-layout">
      <form onSubmit={handleUpload} className="card document-upload-card space-y-4">
        <div className="section-heading-row"><span className="section-heading-icon">↑</span><div><h2>Tải tài liệu mới</h2><p>PDF tối đa 50MB, hệ thống sẽ kiểm tra trước khi xử lý.</p></div></div>
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
              Bạn chưa thuộc lớp nào — vào trang &quot;Lớp học&quot; để tạo hoặc tham gia một lớp trước.
            </p>
          )}
        </div>

        <div className="file-drop-zone">
          <span className="file-drop-zone__icon">⇧</span>
          <label className="mb-1 block text-[11.5px] font-semibold" style={{ color: "var(--ink-soft)" }}>
            {file ? file.name : "Chọn file PDF từ thiết bị"}
          </label>
          <p>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Sẵn sàng tải lên` : "Kéo thả hoặc bấm để chọn · tối đa 50MB"}</p>
          <input
            id="fileInput"
            type="file"
            required
            accept=".pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="file-drop-zone__input"
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

      <aside className="document-process-card">
        <span className="page-visual-hero__eyebrow">Quy trình tự động</span>
        <h3>Từ PDF đến câu trả lời</h3>
        <ol>
          <li><span>1</span><div><strong>Kiểm tra an toàn</strong><p>Định dạng, kích thước và nội dung.</p></div></li>
          <li><span>2</span><div><strong>Phân tích tài liệu</strong><p>Nhận diện cấu trúc và chia đoạn.</p></div></li>
          <li><span>3</span><div><strong>Lập chỉ mục</strong><p>Sẵn sàng tìm kiếm có trích dẫn.</p></div></li>
          <li><span>4</span><div><strong>Duyệt nội dung</strong><p>Giảng viên kiểm soát trước khi dùng.</p></div></li>
        </ol>
      </aside>
      </div>

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

      <p className="document-note mt-5 text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
        Tài liệu tải lên cần giảng viên duyệt trước. Sau khi được duyệt, tài liệu xuất hiện trong
        trang lớp học tương ứng — vào &ldquo;Lớp học&rdquo; › &ldquo;Vào lớp&rdquo; để đọc bản PDF gốc.
      </p>



    </div>
  );
}
