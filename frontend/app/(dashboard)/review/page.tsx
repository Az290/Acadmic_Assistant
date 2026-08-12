"use client";

import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  CoursePublic,
  DocumentPreview,
  DocumentPublic,
  parseCuratorReport,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

/**
 * Trang duyệt tài liệu (HITL - Human In The Loop).
 *
 * Tài liệu upload lên KHÔNG tự động khả dụng cho sinh viên - phải qua
 * đây được giảng viên duyệt. Cảnh báo của Curator Agent (nếu có) hiển
 * thị ngay trên thẻ tài liệu để giảng viên cân nhắc trước khi quyết
 * định, nhưng KHÔNG chặn tự động (xem app/curator/curator.py).
 */
const CURATOR_STEP_LABELS: Record<string, string> = {
  injection_scan: "Chỉ dẫn ẩn",
  quality_gate: "Chất lượng nội dung",
  dedup: "Trùng lặp",
};

function CuratorStepRow({ stepKey, status, detail }: { stepKey: string; status: "pass" | "warn"; detail: string }) {
  const ok = status === "pass";
  return (
    <div className="flex items-start gap-2 py-1">
      <span
        className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
        style={
          ok
            ? { background: "var(--teal-bg, #DCF3EC)", color: "var(--teal-ink, #0F7A5C)" }
            : { background: "var(--amber-bg)", color: "var(--amber-ink)" }
        }
      >
        {ok ? "✓" : "!"}
      </span>
      <div className="min-w-0 text-[12px]">
        <span className="font-semibold">{CURATOR_STEP_LABELS[stepKey] ?? stepKey}: </span>
        <span style={{ color: ok ? "var(--ink-soft)" : "var(--amber-ink)" }}>{detail}</span>
      </div>
    </div>
  );
}

export default function ReviewDocumentsPage() {
  const { user } = useAuth();
  const [courses, setCourses] = useState<CoursePublic[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [documents, setDocuments] = useState<DocumentPublic[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  // Tài liệu đang xem trước (null = không mở modal nào)
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [previewLoadingId, setPreviewLoadingId] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then((list) => {
        const owned = list.filter((c) => c.owner_id === user?.id);
        setCourses(owned);
        if (owned.length > 0) setSelectedCourseId(owned[0].id);
      })
      .catch(() => setCourses([]));
  }, [user?.id]);

  async function loadPending(courseId: number) {
    setLoading(true);
    setError(null);
    try {
      const list = await api.get<DocumentPublic[]>(
        `/v1/instructor/documents/pending?course_id=${courseId}`
      );
      setDocuments(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không tải được hàng chờ duyệt.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (selectedCourseId === null) return;
    loadPending(selectedCourseId);
  }, [selectedCourseId]);

  /**
   * Mở xem trước nội dung ĐÃ TRÍCH XUẤT của tài liệu - giúp giảng viên
   * biết AI thực sự đọc được gì trước khi quyết định duyệt (file PDF
   * scan sẽ ra text rỗng hoặc rác, nhìn bản gốc không phát hiện được).
   */
  async function handlePreview(documentId: number) {
    setPreviewLoadingId(documentId);
    setError(null);
    try {
      const detail = await api.get<DocumentPreview>(`/v1/instructor/documents/${documentId}/preview`);
      setPreview(detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không xem trước được tài liệu.");
    } finally {
      setPreviewLoadingId(null);
    }
  }

  async function handleApprove(documentId: number) {
    setBusyId(documentId);
    setError(null);
    try {
      await api.post(`/v1/instructor/documents/${documentId}/approve`);
      setDocuments((prev) => prev.filter((d) => d.id !== documentId));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không duyệt được tài liệu.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(documentId: number) {
    setBusyId(documentId);
    setError(null);
    try {
      await api.post(`/v1/instructor/documents/${documentId}/reject`, {
        reason: rejectReason.trim() || null,
      });
      setDocuments((prev) => prev.filter((d) => d.id !== documentId));
      setRejectingId(null);
      setRejectReason("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không từ chối được tài liệu.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="max-w-4xl">
      <p className="mb-4 text-[13px]" style={{ color: "var(--ink-soft)" }}>
        Tài liệu tải lên chỉ được sinh viên tra cứu <strong>sau khi bạn duyệt</strong>. Cảnh báo tự
        động (nếu có) chỉ mang tính tham khảo — bạn là người quyết định cuối cùng.
      </p>

      {courses.length === 0 && (
        <div className="card">
          <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
            Bạn chưa phụ trách lớp nào.
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

          {error && (
            <p
              className="mb-3 rounded-[9px] px-3 py-2 text-[13px]"
              style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}
            >
              {error}
            </p>
          )}

          {loading && (
            <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
              Đang tải…
            </p>
          )}

          {!loading && documents.length === 0 && (
            <div className="card">
              <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
                Không có tài liệu nào đang chờ duyệt.
              </p>
            </div>
          )}

          <div className="space-y-3">
            {documents.map((d) => (
              <div key={d.id} className="card">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold">{d.title}</div>
                    <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                      {d.image_count > 0 ? `${d.image_count} ảnh chưa xử lý · ` : ""}
                      Bản quyền: {d.license_status}
                    </div>
                  </div>
                  <span
                    className="whitespace-nowrap rounded-full px-2.5 py-[3px] text-[10.5px] font-bold"
                    style={{ background: "var(--amber-bg)", color: "var(--amber-ink)" }}
                  >
                    Chờ duyệt
                  </span>
                </div>

                {d.curator_notes &&
                  (() => {
                    const report = parseCuratorReport(d.curator_notes);
                    if (report) {
                      return (
                        <div
                          className="mt-2.5 rounded-[9px] border px-3 py-1.5"
                          style={{ background: "var(--bg-soft, #FAFAF8)", borderColor: "var(--border)" }}
                        >
                          <CuratorStepRow
                            stepKey="injection_scan"
                            status={report.injection_scan.status}
                            detail={report.injection_scan.detail}
                          />
                          <CuratorStepRow
                            stepKey="quality_gate"
                            status={report.quality_gate.status}
                            detail={report.quality_gate.detail}
                          />
                          <CuratorStepRow stepKey="dedup" status={report.dedup.status} detail={report.dedup.detail} />
                        </div>
                      );
                    }
                    // Dữ liệu cũ (ingest trước khi đổi sang schema JSON) - hiển thị thô để không mất thông tin.
                    return (
                      <div
                        className="mt-2.5 whitespace-pre-line rounded-[9px] border px-3 py-2 text-[12px]"
                        style={{
                          background: "var(--amber-bg)",
                          borderColor: "#F0D589",
                          color: "var(--amber-ink)",
                        }}
                      >
                        {d.curator_notes}
                      </div>
                    );
                  })()}

                {d.rejection_reason && (
                  <div
                    className="mt-2 rounded-[9px] border px-3 py-2 text-[12px]"
                    style={{ background: "var(--red-bg)", borderColor: "#E9B8B8", color: "var(--red-ink)" }}
                  >
                    <span className="font-semibold">Lý do từ chối: </span>
                    {d.rejection_reason}
                  </div>
                )}

                {rejectingId === d.id ? (
                  <div className="mt-3 flex gap-2 border-t pt-3" style={{ borderColor: "var(--border)" }}>
                    <input
                      type="text"
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      placeholder="Lý do từ chối (không bắt buộc)"
                      className="flex-1 rounded-[7px] border px-2.5 py-1.5 text-[12.5px] focus:outline-none"
                      style={{ borderColor: "var(--border-strong)" }}
                    />
                    <button
                      onClick={() => handleReject(d.id)}
                      disabled={busyId === d.id}
                      className="rounded-[7px] px-3 py-1.5 text-[12.3px] font-semibold text-white disabled:opacity-50"
                      style={{ background: "var(--red)" }}
                    >
                      Xác nhận từ chối
                    </button>
                    <button
                      onClick={() => {
                        setRejectingId(null);
                        setRejectReason("");
                      }}
                      className="rounded-[7px] border px-3 py-1.5 text-[12.3px] font-semibold"
                      style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                    >
                      Huỷ
                    </button>
                  </div>
                ) : (
                  <div className="mt-3 flex gap-2 border-t pt-3" style={{ borderColor: "var(--border)" }}>
                    <button
                      onClick={() => handleApprove(d.id)}
                      disabled={busyId === d.id}
                      className="rounded-[7px] px-4 py-1.5 text-[12.3px] font-semibold text-white disabled:opacity-50"
                      style={{ background: "var(--teal)" }}
                    >
                      {busyId === d.id ? "Đang xử lý…" : "Duyệt"}
                    </button>
                    <button
                      onClick={() => setRejectingId(d.id)}
                      disabled={busyId === d.id}
                      className="rounded-[7px] border px-4 py-1.5 text-[12.3px] font-semibold disabled:opacity-50"
                      style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                    >
                      Từ chối
                    </button>
                    <button
                      onClick={() => handlePreview(d.id)}
                      disabled={previewLoadingId === d.id}
                      className="rounded-[7px] border px-4 py-1.5 text-[12.3px] font-semibold disabled:opacity-50"
                      style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
                    >
                      {previewLoadingId === d.id ? "Đang tải…" : "Xem trước"}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* Modal xem trước - hiện TEXT ĐÃ TRÍCH XUẤT (thứ AI thực sự đọc
          được), không phải file PDF gốc. */}
      {preview && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          style={{ background: "rgba(10, 12, 30, 0.45)" }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setPreview(null);
          }}
        >
          <div
            className="max-h-[85vh] w-[680px] max-w-[94vw] overflow-y-auto rounded-xl border bg-white p-5"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[13px] font-bold">{preview.title}</div>
                <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                  {preview.total_chunks} đoạn đã trích xuất
                  {preview.image_count > 0 && ` · ${preview.image_count} ảnh chưa xử lý được`}
                </div>
              </div>
              <button
                onClick={() => setPreview(null)}
                className="text-[16px] leading-none"
                style={{ color: "var(--ink-faint)" }}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>

            <p
              className="mb-3 rounded-[9px] px-3 py-2 text-[11.5px]"
              style={{ background: "var(--accent-bg)", color: "var(--accent-ink)" }}
            >
              Đây là nội dung <strong>AI thực sự đọc được</strong> sau khi trích xuất — nếu thấy trống hoặc
              lộn xộn, tài liệu có thể là bản scan và AI sẽ không dùng được.
            </p>

            {preview.chunks.length === 0 && (
              <p className="text-[12.5px]" style={{ color: "var(--red-ink)" }}>
                Không trích xuất được đoạn văn bản nào từ tài liệu này.
              </p>
            )}

            {preview.chunks.map((c, i) => (
              <div key={c.chunk_id} className="mb-2.5">
                <div className="mb-1 text-[10.5px] font-semibold" style={{ color: "var(--ink-faint)" }}>
                  Đoạn {i + 1}
                  {c.page_number !== null && ` · trang ${c.page_number}`}
                </div>
                <div
                  className="whitespace-pre-wrap rounded-[9px] border p-3 text-[12px] leading-relaxed"
                  style={{ background: "#F8F9FE", borderColor: "var(--border)" }}
                >
                  {c.content}
                </div>
              </div>
            ))}

            {preview.total_chunks > preview.chunks.length && (
              <p className="mt-2 text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
                Hiển thị {preview.chunks.length} đoạn đầu trong tổng số {preview.total_chunks} đoạn.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
