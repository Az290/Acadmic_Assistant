"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError, CoursePublic, DocumentSummary } from "@/lib/api";

/**
 * Trang chi tiết 1 lớp - nơi sinh viên THỰC SỰ vào để học: xem tài liệu
 * của đúng lớp đó.
 *
 * TẠI SAO TÁCH KHỎI trang /documents: trang đó giờ chỉ còn nhiệm vụ TẢI
 * LÊN (nhãn sidebar đổi thành "Thêm tài liệu"). Người học tìm tài liệu
 * theo LỚP chứ không theo "kho tài liệu chung" - vào lớp rồi mới thấy
 * tài liệu lớp đó là luồng tự nhiên, giống mọi LMS thật.
 *
 * Đọc bản PDF GỐC (nhúng iframe) thay vì nội dung đã chunk: chunk là
 * định dạng phục vụ MÁY tra cứu (cắt vụn, mất bố cục/hình/bảng), người
 * đọc gần như không hiểu gì - xem GET /v1/documents/{id}/file ở backend.
 */
export default function CourseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = Number(params.courseId);

  const [course, setCourse] = useState<CoursePublic | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Tài liệu đang mở đọc (null = chưa mở gì). Lưu cả title để hiện tên
  // trên thanh tiêu đề của khung đọc.
  const [reading, setReading] = useState<DocumentSummary | null>(null);

  useEffect(() => {
    if (!Number.isFinite(courseId)) return;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        // Lấy tên lớp từ danh sách lớp của chính mình - không có endpoint
        // GET /v1/courses/{id} riêng, và cũng không cần: danh sách này
        // đã đảm bảo người dùng THUỘC lớp mới thấy được.
        const myCourses = await api.get<CoursePublic[]>("/v1/courses/me");
        const found = myCourses.find((c) => c.id === courseId) ?? null;
        setCourse(found);
        if (found === null) {
          setError("Bạn không thuộc lớp này hoặc lớp không tồn tại.");
          return;
        }
        setDocuments(await api.get<DocumentSummary[]>(`/v1/documents?course_id=${courseId}`));
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "Không tải được thông tin lớp học.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [courseId]);

  const fileUrl = reading
    ? `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001"}/v1/documents/${reading.id}/file`
    : null;

  return (
    <div className="max-w-5xl">
      <button
        onClick={() => router.push("/courses")}
        className="mb-3 text-[12px] font-semibold"
        style={{ color: "var(--accent-strong)" }}
      >
        ← Tất cả lớp học
      </button>

      {loading && (
        <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
          Đang tải…
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

      {course && (
        <>
          <div className="mb-4">
            <div className="text-[11px] font-semibold" style={{ color: "var(--ink-faint)" }}>
              {course.code}
            </div>
            <h1 className="text-page-title">{course.name}</h1>
            <p className="text-support mt-1">
              Tài liệu của lớp — đọc bản gốc để nắm kiến thức, rồi hỏi Nova những chỗ chưa rõ.
            </p>
          </div>

          {documents.length === 0 && !error && (
            <div className="card">
              <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
                Lớp này chưa có tài liệu nào được duyệt. Bạn có thể đóng góp tài liệu ở trang
                &ldquo;Thêm tài liệu&rdquo;.
              </p>
            </div>
          )}

          <div className="space-y-2.5">
            {documents.map((d) => (
              <div key={d.id} className="card flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold">{d.title}</div>
                  <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                    {d.uploaded_by_name} · {new Date(d.created_at).toLocaleDateString("vi-VN")}
                    {d.image_count > 0 && ` · ${d.image_count} hình`}
                  </div>
                </div>
                <button
                  onClick={() => setReading(d)}
                  className="shrink-0 rounded-[7px] px-4 py-1.5 text-[12.3px] font-semibold text-white"
                  style={{ background: "var(--accent)" }}
                >
                  Đọc tài liệu
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Khung đọc PDF gốc - chiếm gần hết màn hình vì đây là lúc người
          học ĐANG ĐỌC, không cần thấy gì khác phía sau. */}
      {reading && fileUrl && (
        <div
          className="fixed inset-0 z-[100] flex flex-col p-4"
          style={{ background: "rgba(10, 12, 30, 0.6)" }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setReading(null);
          }}
        >
          <div className="mx-auto flex h-full w-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white">
            <div
              className="flex items-center justify-between gap-3 border-b px-4 py-2.5"
              style={{ borderColor: "var(--border)" }}
            >
              <div className="min-w-0 text-[13px] font-semibold">{reading.title}</div>
              <div className="flex shrink-0 items-center gap-2">
                <a
                  href={fileUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-[7px] border px-3 py-1 text-[11.5px] font-semibold"
                  style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                >
                  Mở tab mới
                </a>
                <button
                  onClick={() => setReading(null)}
                  className="text-[16px] leading-none"
                  style={{ color: "var(--ink-faint)" }}
                  aria-label="Đóng"
                >
                  ✕
                </button>
              </div>
            </div>
            {/* iframe dùng trình đọc PDF sẵn có của trình duyệt - giữ
                nguyên bố cục, hình ảnh, bảng biểu như bản gốc. */}
            <iframe src={fileUrl} title={reading.title} className="flex-1 border-0" />
          </div>
        </div>
      )}
    </div>
  );
}
