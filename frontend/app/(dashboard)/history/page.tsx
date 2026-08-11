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

  return (
    <div className="max-w-4xl">
      <div className="card !p-0">
        <div className="border-b px-4 py-3 text-[12.5px] font-bold" style={{ borderColor: "var(--border)" }}>
          Lịch sử câu hỏi
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
          <p className="px-4 py-3 text-[13px]" style={{ color: "var(--ink-faint)" }}>
            Bạn chưa hỏi câu nào. Bấm biểu tượng chat ở góc phải dưới để bắt đầu.
          </p>
        )}

        {items.length > 0 && (
          <table className="w-full text-[12.5px]">
            <thead>
              <tr style={{ color: "var(--ink-faint)" }}>
                <th className="px-4 py-2 text-left text-[10.5px] font-bold uppercase tracking-wide">Câu hỏi</th>
                <th className="px-3 py-2 text-left text-[10.5px] font-bold uppercase tracking-wide">Agent</th>
                <th className="px-3 py-2 text-left text-[10.5px] font-bold uppercase tracking-wide">Thời gian</th>
                <th className="px-4 py-2 text-left text-[10.5px] font-bold uppercase tracking-wide">Nguồn</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, i) => (
                <tr key={i} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="max-w-[320px] truncate px-4 py-2.5" title={item.question}>
                    {item.question}
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className="rounded-full px-2.5 py-[3px] text-[10.5px] font-bold"
                      style={CATEGORY_STYLE[item.category]}
                    >
                      {CATEGORY_LABEL[item.category]}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap" style={{ color: "var(--ink-soft)" }}>
                    {formatRelativeTime(item.created_at)}
                  </td>
                  <td className="px-4 py-2.5" style={{ color: "var(--ink-soft)" }}>
                    {formatSource(item)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
