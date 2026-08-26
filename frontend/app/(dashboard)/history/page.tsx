"use client";

import { useEffect, useState } from "react";
import { api, ApiError, ConversationHistoryItem, MessageCategory } from "@/lib/api";

const CATEGORY_LABEL: Record<MessageCategory, string> = {
  RAG_QUESTION: "Academic",
  SOCRATIC_REQUEST: "Tutor",
  CHITCHAT: "Trò chuyện",
  OFF_TOPIC: "Ngoài phạm vi",
};

const CATEGORY_STYLE: Record<MessageCategory, React.CSSProperties> = {
  RAG_QUESTION: { background: "var(--accent-bg)", color: "var(--accent-ink)" },
  SOCRATIC_REQUEST: { background: "var(--blue-bg)", color: "var(--blue-ink)" },
  CHITCHAT: { background: "#E8EAF0", color: "var(--ink-soft)" },
  OFF_TOPIC: { background: "var(--amber-bg)", color: "var(--amber-ink)" },
};

/** Thời gian tương đối kiểu "5 phút trước" - đủ vài mốc phổ biến, không cần thư viện ngoài. */
function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "Vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Hôm qua";
  if (days < 7) return `${days} ngày trước`;
  return new Date(iso).toLocaleDateString("vi-VN");
}

function formatSource(item: ConversationHistoryItem): string {
  if (item.source_count === null) return "—";
  if (item.category === "SOCRATIC_REQUEST") return `Socratic (${item.source_count} lượt)`;
  return item.source_count === 0 ? "Không tìm thấy tài liệu" : `${item.source_count} trích dẫn`;
}

/**
 * Lịch sử hỏi đáp của CHÍNH sinh viên - chỉ hiện các lượt đã lưu thành
 * công (không hiện câu bị Guardrail chặn - hệ thống hiện KHÔNG lưu lại
 * các câu đó, xem docstring app/profile/router.py::get_conversation_history()).
 */
export default function HistoryPage() {
  const [items, setItems] = useState<ConversationHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<ConversationHistoryItem[]>("/v1/profile/history")
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Không tải được lịch sử."))
      .finally(() => setLoading(false));
  }, []);

  const citedCount = items.filter((item) => (item.source_count ?? 0) > 0).length;
  const tutorCount = items.filter((item) => item.category === "SOCRATIC_REQUEST").length;

  return (
    <div className="history-page max-w-4xl">
      <section className="page-visual-hero page-visual-hero--history">
        <div><span className="page-visual-hero__eyebrow">Nhật ký học tập</span><h2>Hành trình cùng Nova</h2><p>Tìm lại câu hỏi, phương pháp học và nguồn tài liệu bạn đã sử dụng.</p></div>
        <div className="history-summary">
          <div><strong>{items.length}</strong><span>Lượt hỏi</span></div>
          <div><strong>{citedCount}</strong><span>Có trích dẫn</span></div>
          <div><strong>{tutorCount}</strong><span>Phiên gia sư</span></div>
        </div>
      </section>

      <div className="history-content">
        <div className="section-heading-row">
          <span className="section-heading-icon">◷</span>
          <div><h2>Lịch sử câu hỏi</h2><p>Các hoạt động gần đây nhất của bạn.</p></div>
        </div>

        {loading && (
          <p className="px-4 py-3 text-[13px]" style={{ color: "var(--ink-faint)" }}>
            Đang tải…
          </p>
        )}
        {error && (
          <p className="px-4 py-3 text-[13px]" style={{ color: "var(--red-ink)" }}>
            {error}
          </p>
        )}
        {!loading && !error && items.length === 0 && (
          <div className="visual-empty-state"><span className="visual-empty-state__icon">?</span><h3>Chưa có cuộc trò chuyện</h3><p>Bấm biểu tượng Nova ở góc phải để đặt câu hỏi đầu tiên.</p></div>
        )}

        {items.length > 0 && (
          <div className="history-timeline">
              {items.map((item, i) => (
                <article key={i} className="history-item">
                  <span className="history-item__visual" aria-hidden="true">{item.category === "SOCRATIC_REQUEST" ? "✦" : item.category === "RAG_QUESTION" ? "?" : "·"}</span>
                  <div className="history-item__body">
                    <div className="history-item__topline">
                    <span
                      className="rounded-full px-2.5 py-[3px] text-[10.5px] font-bold"
                      style={CATEGORY_STYLE[item.category]}
                    >
                      {CATEGORY_LABEL[item.category]}
                    </span>
                      <span>{formatRelativeTime(item.created_at)}</span>
                    </div>
                    <h3 title={item.question}>{item.question}</h3>
                    <div className="history-item__source"><span>⌁</span>{formatSource(item)}</div>
                  </div>
                </article>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
