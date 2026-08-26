"use client";

import { useState, useEffect } from "react";
import { api, ApiError, CoursePublic, DocumentContent, DocumentPublic, DocumentSummary } from "@/lib/api";

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

  // Lớp đang chọn để XEM LẠI tài liệu đã duyệt (khác courseId dùng cho
  // form upload ở trên - sinh viên có thể muốn đọc tài liệu lớp A trong
  // khi đang upload cho lớp B).
  const [browseCourseId, setBrowseCourseId] = useState<number | "">("");
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsError, setDocsError] = useState<string | null>(null);
  // Tài liệu đang xem nội dung (null = không mở modal nào)
  const [content, setContent] = useState<DocumentContent | null>(null);
  const [contentLoadingId, setContentLoadingId] = useState<number | null>(null);
  const [contentError, setContentError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then((list) => {
        setCourses(list);
        if (list.length > 0) setBrowseCourseId(list[0].id);
      })
      .catch(() => setCourses([]));
  }, []);

  async function loadDocuments(id: number) {
    setDocsLoading(true);
    setDocsError(null);
    try {
      const list = await api.get<DocumentSummary[]>(`/v1/documents?course_id=${id}`);
      setDocuments(list);
    } catch (err) {
      setDocsError(err instanceof ApiError ? err.detail : "Không tải được danh sách tài liệu.");
    } finally {
      setDocsLoading(false);
    }
  }

  useEffect(() => {
    if (browseCourseId === "") return;
    loadDocuments(browseCourseId);
  }, [browseCourseId]);

  async function handleReadContent(documentId: number) {
    setContentLoadingId(documentId);
    setContentError(null);
    try {
      const detail = await api.get<DocumentContent>(`/v1/documents/${documentId}/content`);
      setContent(detail);
    } catch (err) {
      setContentError(err instanceof ApiError ? err.detail : "Không đọc được nội dung tài liệu này.");
    } finally {
      setContentLoadingId(null);
    }
  }

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
        Ghi chú: hệ thống hiện chưa có endpoint tải lại file PDF gốc — chỉ đọc được nội dung đã trích
        xuất (văn bản AI thực sự dùng để trả lời).
      </p>

      {/* Kho tài liệu đã duyệt của lớp - đây là chỗ sinh viên THỰC SỰ
          xem lại được kiến thức của lớp để biết nên hỏi Nova điều gì. */}
      <div className="mt-8">
        <div className="section-heading-row">
          <span className="section-heading-icon">📚</span>
          <div>
            <h2>Tài liệu của lớp</h2>
            <p>Xem lại nội dung đã trích xuất từ tài liệu đã được giảng viên duyệt.</p>
          </div>
        </div>

        <div className="mt-3">
          <label className="mb-1 block text-[11.5px] font-semibold" style={{ color: "var(--ink-soft)" }}>
            Chọn lớp
          </label>
          <select
            value={browseCourseId}
            onChange={(e) => setBrowseCourseId(e.target.value ? Number(e.target.value) : "")}
            className="w-full max-w-sm rounded-[7px] border px-2.5 py-2 text-[12.5px] focus:outline-none"
            style={{ borderColor: "var(--border-strong)" }}
          >
            <option value="">— Chọn lớp —</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.code})
              </option>
            ))}
          </select>
        </div>

        {docsError && (
          <p
            className="mt-3 rounded-[9px] px-3 py-2 text-[12.5px]"
            style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
          >
            {docsError}
          </p>
        )}

        {docsLoading && (
          <p className="mt-3 text-[13px]" style={{ color: "var(--ink-faint)" }}>
            Đang tải…
          </p>
        )}

        {!docsLoading && browseCourseId !== "" && documents.length === 0 && !docsError && (
          <div className="card mt-3">
            <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
              Lớp này chưa có tài liệu nào đã được duyệt.
            </p>
          </div>
        )}

        {!docsLoading && documents.length > 0 && (
          <div className="mt-3 space-y-2">
            {documents.map((d) => (
              <div key={d.id} className="card flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold">{d.title}</div>
                  <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                    {d.uploaded_by_name} · {new Date(d.created_at).toLocaleDateString("vi-VN")} ·{" "}
                    {d.chunk_count} đoạn nội dung
                  </div>
                </div>
                <button
                  onClick={() => handleReadContent(d.id)}
                  disabled={contentLoadingId === d.id}
                  className="shrink-0 rounded-[7px] border px-3.5 py-1.5 text-[12.3px] font-semibold disabled:opacity-50"
                  style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                >
                  {contentLoadingId === d.id ? "Đang tải…" : "Đọc nội dung"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {contentError && (
        <p
          className="mt-3 rounded-[9px] px-3 py-2 text-[12.5px]"
          style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
        >
          {contentError}
        </p>
      )}

      {/* Modal đọc nội dung - cùng pattern với modal xem trước ở trang
          review/page.tsx để giao diện nhất quán trong toàn hệ thống. */}
      {content && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          style={{ background: "rgba(10, 12, 30, 0.45)" }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setContent(null);
          }}
        >
          <div
            className="max-h-[85vh] w-[680px] max-w-[94vw] overflow-y-auto rounded-xl border bg-white p-5"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[13px] font-bold">{content.title}</div>
                <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                  {content.total_chunks} đoạn nội dung
                </div>
              </div>
              <button
                onClick={() => setContent(null)}
                className="text-[16px] leading-none"
                style={{ color: "var(--ink-faint)" }}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>

            {content.chunks.map((c) => (
              <div key={c.chunk_id} className="mb-2.5">
                {(c.context_prefix || c.page_number !== null) && (
                  <div className="mb-1 text-[10.5px] font-semibold" style={{ color: "var(--ink-faint)" }}>
                    {c.context_prefix ?? ""}
                    {c.context_prefix && c.page_number !== null && " · "}
                    {c.page_number !== null && `trang ${c.page_number}`}
                  </div>
                )}
                <div
                  className="whitespace-pre-wrap rounded-[9px] border p-3 text-[12px] leading-relaxed"
                  style={{ background: "var(--panel-soft, #F8F9FE)", borderColor: "var(--border)" }}
                >
                  {c.content}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
