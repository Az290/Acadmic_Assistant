"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, CitationPublic, streamChat } from "@/lib/api";

/**
 * ChatBubble - panel chat nổi kiểu Messenger, hiện ở MỌI trang (được
 * đặt trong DashboardLayout, ngoài <main>) thay vì là 1 trang /chat
 * riêng biệt - đúng theo yêu cầu prototype: người dùng không cần rời
 * trang đang xem để hỏi, và có thể thu nhỏ lại khi không cần.
 *
 * 2 chế độ trong panel ("Hỏi đáp" / "Gia sư") ứng với force_category
 * gửi kèm mỗi request - mỗi tab giữ conversation_id RIÊNG (2 phiên
 * hội thoại độc lập), tránh trộn lẫn lịch sử giữa 2 kiểu trả lời khác
 * hẳn nhau (RAG_QUESTION trả lời thẳng vs SOCRATIC_REQUEST gợi mở).
 */

type PanelSize = "closed" | "compact" | "half" | "full";
type TabMode = "RAG_QUESTION" | "SOCRATIC_REQUEST";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  citations?: CitationPublic[];
  blocked?: boolean;
  streaming?: boolean;
}

interface TabState {
  messages: DisplayMessage[];
  conversationId: number | undefined;
}

const TAB_LABEL: Record<TabMode, string> = {
  RAG_QUESTION: "Hỏi đáp",
  SOCRATIC_REQUEST: "Gia sư",
};

// Đúng 3 cỡ theo prototype (.ai-panel / .ai-panel.half / .ai-panel.full)
// - "compact" là cỡ MẶC ĐỊNH của prototype (360x520), "half" chiếm
// nửa màn hình, "full" gần toàn màn hình (trừ bề rộng sidebar 240px).
const PANEL_SIZE_CLASS: Record<Exclude<PanelSize, "closed">, string> = {
  compact: "h-[520px] w-[360px]",
  half: "h-[75vh] w-[55vw]",
  full: "h-screen w-[calc(100vw-240px)]",
};

function emptyTabState(): TabState {
  return { messages: [], conversationId: undefined };
}

export default function ChatBubble() {
  const [size, setSize] = useState<PanelSize>("closed");
  const [tab, setTab] = useState<TabMode>("RAG_QUESTION");
  const [tabs, setTabs] = useState<Record<TabMode, TabState>>({
    RAG_QUESTION: emptyTabState(),
    SOCRATIC_REQUEST: emptyTabState(),
  });
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const isOpen = size !== "closed";
  const current = tabs[tab];

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [tabs, tab]);

  function updateCurrentTab(updater: (state: TabState) => TabState) {
    setTabs((prev) => ({ ...prev, [tab]: updater(prev[tab]) }));
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;

    const activeTab = tab; // chốt lại tab tại thời điểm gửi - tránh lỗi nếu người dùng đổi tab giữa lúc đang stream
    setTabs((prev) => ({
      ...prev,
      [activeTab]: {
        ...prev[activeTab],
        messages: [...prev[activeTab].messages, { role: "user", content: text }, { role: "assistant", content: "", streaming: true }],
      },
    }));
    setInput("");
    setSending(true);
    setError(null);

    try {
      await streamChat(
        {
          message: text,
          conversation_id: tabs[activeTab].conversationId,
          force_category: activeTab,
        },
        (event) => {
          setTabs((prev) => {
            const state = prev[activeTab];
            const messages = [...state.messages];
            const lastIndex = messages.length - 1;

            if (event.type === "start") {
              return { ...prev, [activeTab]: { messages, conversationId: event.conversation_id } };
            }
            if (event.type === "chunk") {
              messages[lastIndex] = {
                ...messages[lastIndex],
                content: messages[lastIndex].content + event.text,
              };
              return { ...prev, [activeTab]: { ...state, messages } };
            }
            if (event.type === "done") {
              messages[lastIndex] = { ...messages[lastIndex], citations: event.citations, streaming: false };
              return { ...prev, [activeTab]: { ...state, messages } };
            }
            if (event.type === "blocked") {
              messages[lastIndex] = {
                role: "assistant",
                content: "Câu hỏi của bạn không hợp lệ, vui lòng đặt câu hỏi khác.",
                blocked: true,
                streaming: false,
              };
              return {
                ...prev,
                [activeTab]: { messages, conversationId: event.conversation_id || state.conversationId },
              };
            }
            return prev;
          });

          // Badge chỉ tăng khi panel ĐANG ĐÓNG và tin nhắn đã hoàn tất -
          // đúng ý "thông báo chủ động" của prototype (bong bóng số đỏ),
          // không tăng liên tục theo từng chunk khi panel đang mở (đang
          // xem trực tiếp thì không cần badge).
          if (event.type === "done" && size === "closed") {
            setUnreadCount((c) => c + 1);
          }
        }
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : "Không thể gửi câu hỏi, vui lòng thử lại.";
      setError(message);
      updateCurrentTab((state) => ({
        ...state,
        messages: state.messages.slice(0, -1), // bỏ bong bóng "đang trả lời" rỗng nếu lỗi xảy ra trước khi có chunk nào
      }));
    } finally {
      setSending(false);
    }
  }

  function openPanel() {
    setSize((prev) => (prev === "closed" ? "compact" : prev));
    setUnreadCount(0);
  }

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
      {isOpen && (
        <div
          className={`flex flex-col overflow-hidden rounded-2xl border shadow-2xl transition-all ${PANEL_SIZE_CLASS[size]}`}
          style={{ background: "#ffffff", borderColor: "var(--sidebar-line)" }}
        >
          {/* Header: tiêu đề + nút đổi cỡ + nút đóng */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ background: "var(--sidebar)" }}
          >
            <span className="text-sm font-semibold text-white">Trợ lý học thuật</span>
            <div className="flex items-center gap-1">
              {(["compact", "half", "full"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSize(s)}
                  className="rounded px-1.5 py-0.5 text-[10px] font-medium"
                  style={{
                    color: size === s ? "#ffffff" : "var(--sidebar-ink)",
                    background: size === s ? "var(--accent)" : "transparent",
                  }}
                  title={s === "compact" ? "Thu nhỏ" : s === "half" ? "Vừa" : "Phóng to"}
                >
                  {s === "compact" ? "S" : s === "half" ? "M" : "L"}
                </button>
              ))}
              <button
                onClick={() => setSize("closed")}
                className="ml-1 rounded px-2 py-0.5 text-xs font-bold text-white hover:opacity-70"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Tabs: Hỏi đáp / Gia sư */}
          <div className="flex border-b border-slate-200">
            {(["RAG_QUESTION", "SOCRATIC_REQUEST"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="flex-1 py-2 text-xs font-semibold transition-colors"
                style={
                  tab === t
                    ? { color: "var(--accent)", borderBottom: "2px solid var(--accent)" }
                    : { color: "#94a3b8", borderBottom: "2px solid transparent" }
                }
              >
                {TAB_LABEL[t]}
              </button>
            ))}
          </div>

          {/* Nội dung chat */}
          <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
            {current.messages.length === 0 && (
              <p className="text-xs text-slate-400">
                {tab === "RAG_QUESTION"
                  ? "Đặt câu hỏi về nội dung môn học — hệ thống tra cứu tài liệu để trả lời trực tiếp."
                  : "Chế độ Gia sư: hệ thống sẽ gợi mở, dẫn dắt bạn tự tìm ra câu trả lời thay vì đưa đáp án ngay."}
              </p>
            )}

            {current.messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-3 py-2 text-xs leading-relaxed ${
                    m.role === "user"
                      ? "text-white"
                      : m.blocked
                        ? "border border-red-200 bg-red-50 text-red-800"
                        : "border border-slate-200 bg-slate-50 text-slate-800"
                  }`}
                  style={m.role === "user" ? { background: "var(--accent)" } : undefined}
                >
                  <div className="whitespace-pre-wrap">
                    {m.content}
                    {m.streaming && <span className="animate-pulse">▍</span>}
                  </div>

                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {m.citations.map((c) => (
                        <span
                          key={c.chunk_id}
                          className="rounded bg-blue-50 px-1.5 py-0.5 text-[9px] font-medium text-blue-700"
                          title={`Tài liệu #${c.document_id}${c.page_number ? `, trang ${c.page_number}` : ""}`}
                        >
                          #{c.chunk_id}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={scrollRef} />
          </div>

          {error && <p className="px-3 pb-1 text-[11px] text-red-600">{error}</p>}

          {/* Ô nhập */}
          <div className="flex gap-2 border-t border-slate-200 p-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Nhập câu hỏi…"
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-xs focus:outline-none"
              style={{ borderColor: "#cbd5e1" }}
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="rounded-lg px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              style={{ background: "var(--accent)" }}
            >
              Gửi
            </button>
          </div>
        </div>
      )}

      {/* Bong bóng tròn - luôn hiện, badge số đỏ khi có tin nhắn chưa xem */}
      <button
        onClick={isOpen ? () => setSize("closed") : openPanel}
        className="relative flex h-14 w-14 items-center justify-center rounded-full shadow-xl transition-transform hover:scale-105"
        style={{ background: "var(--accent)" }}
        aria-label="Mở trợ lý học thuật"
      >
        <span className="text-2xl text-white">{isOpen ? "✕" : "💬"}</span>
        {!isOpen && unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>
    </div>
  );
}
