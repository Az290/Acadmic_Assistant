"use client";

import { useEffect, useState } from "react";
import { api, ApiError, CoursePublic, DocumentPublic } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

/**
 * Trang duyệt tài liệu (HITL - Human In The Loop).
 *
 * Tài liệu upload lên KHÔNG tự động khả dụng cho sinh viên - phải qua
 * đây được giảng viên duyệt. Cảnh báo của Curator Agent (nếu có) hiển
 * thị ngay trên thẻ tài liệu để giảng viên cân nhắc trước khi quyết
 * định, nhưng KHÔNG chặn tự động (xem app/curator/curator.py).
 */
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

                {d.curator_notes && (
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
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
