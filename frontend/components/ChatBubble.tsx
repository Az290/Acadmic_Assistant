"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, CitationPublic, ConceptPublic, CoursePublic, streamChat } from "@/lib/api";

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
  const [courses, setCourses] = useState<CoursePublic[]>([]);
  // Lớp đang hỏi - gửi kèm mỗi request để hội thoại được gắn ĐÚNG lớp
  // (phục vụ thống kê Dashboard giảng viên). Nếu để trống, backend tự
  // suy ra từ tài liệu tra cứu được (xem _infer_course_id ở backend).
  const [courseId, setCourseId] = useState<number | undefined>(undefined);
  // Chế độ Gia sư: khái niệm đang học. `detectedConceptId` là kết quả
  // hệ thống TỰ NHẬN DIỆN từ câu hỏi; `conceptId` là lựa chọn TƯỜNG
  // MINH của sinh viên (khi họ sửa lại vì hệ thống đoán sai) - lựa
  // chọn tường minh luôn được ưu tiên khi gửi lên server.
  const [concepts, setConcepts] = useState<ConceptPublic[]>([]);
  const [conceptId, setConceptId] = useState<number | undefined>(undefined);
  const [detectedConceptId, setDetectedConceptId] = useState<number | null>(null);
  // Khái niệm cần CHỌN SẴN ngay khi danh sách concepts của 1 lớp vừa
  // tải xong (đến từ sự kiện "open-tutor-chat" - đổi courseId ngay lúc
  // đó sẽ kích hoạt effect load lại concepts VÀ effect đó tự reset
  // conceptId về undefined, nên không thể set conceptId ngay lập tức
  // cùng lúc với courseId - phải đợi qua bước trung gian này).
  const [pendingConceptId, setPendingConceptId] = useState<number | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  const isOpen = size !== "closed";
  const current = tabs[tab];

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [tabs, tab]);

  useEffect(() => {
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then(setCourses)
      .catch(() => setCourses([]));
  }, []);

  // Danh sách khái niệm chỉ có ý nghĩa khi đã chọn 1 lớp cụ thể - mỗi
  // lớp có bộ khái niệm riêng do giảng viên lớp đó tạo.
  useEffect(() => {
    setConceptId(pendingConceptId);
    setPendingConceptId(undefined);
    setDetectedConceptId(null);
    if (courseId === undefined) {
      setConcepts([]);
      return;
    }
    api
      .get<ConceptPublic[]>(`/v1/concepts?course_id=${courseId}`)
      .then(setConcepts)
      .catch(() => setConcepts([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

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
          course_id: courseId,
          force_category: activeTab,
          // Chỉ gửi khi ở chế độ Gia sư - chế độ Hỏi đáp không dùng
          // khái niệm để điều chỉnh cách trả lời.
          concept_id: activeTab === "SOCRATIC_REQUEST" ? conceptId : undefined,
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

          // Cho sinh viên thấy hệ thống hiểu câu hỏi thuộc khái niệm
          // nào, để họ sửa lại nếu đoán sai.
          if (event.type === "start") {
            setDetectedConceptId(event.concept_id);
          }

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

  // Lắng nghe sự kiện "mở chat ở tab Gia sư với 1 khái niệm cụ thể" -
  // phát ra từ Proactive AI Toast (components/WeakestConceptToast.tsx)
  // khi sinh viên bấm "Hỏi gia sư". Dùng CustomEvent thay vì Context/
  // props-drilling: ChatBubble và Toast không có quan hệ cha-con trực
  // tiếp trong cây component (Toast nằm trong từng trang, ChatBubble
  // nằm trong layout dùng chung) - event trên window là cách đơn giản
  // nhất để 2 component "xa nhau" giao tiếp mà không phải nâng state
  // chat lên tận layout (sẽ phá vỡ việc ChatBubble tự quản lý state
  // riêng của nó).
  useEffect(() => {
    function handleOpenTutorChat(e: Event) {
      const detail = (e as CustomEvent<{ courseId: number; conceptId: number }>).detail;
      setTab("SOCRATIC_REQUEST");
      if (detail.courseId === courseId) {
        // Cùng lớp đang chọn sẵn - effect [courseId] KHÔNG re-run (giá
        // trị không đổi), nên set thẳng conceptId ở đây thay vì đợi effect.
        setConceptId(detail.conceptId);
      } else {
        setPendingConceptId(detail.conceptId);
        setCourseId(detail.courseId); // kích hoạt effect load concepts + áp dụng pendingConceptId ở trên
      }
      setSize((prev) => (prev === "closed" ? "compact" : prev));
      setUnreadCount(0);
    }
    window.addEventListener("open-tutor-chat", handleOpenTutorChat);
    return () => window.removeEventListener("open-tutor-chat", handleOpenTutorChat);
  }, [courseId]);

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

          {/* Chọn lớp đang hỏi - để trống thì hệ thống tự nhận diện */}
          {courses.length > 0 && (
            <div className="border-b px-3 py-1.5" style={{ borderColor: "var(--border)", background: "#F8F9FE" }}>
              <select
                value={courseId ?? ""}
                onChange={(e) => setCourseId(e.target.value ? Number(e.target.value) : undefined)}
                className="w-full bg-transparent text-[11px] focus:outline-none"
                style={{ color: "var(--ink-soft)" }}
              >
                <option value="">Tất cả lớp (tự nhận diện)</option>
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Chế độ Gia sư: khái niệm đang học - hệ thống tự nhận diện,
              sinh viên sửa lại được nếu đoán sai */}
          {tab === "SOCRATIC_REQUEST" && concepts.length > 0 && (
            <div
              className="flex items-center gap-2 border-b px-3 py-1.5"
              style={{ borderColor: "var(--border)", background: "#F8F9FE" }}
            >
              <span className="whitespace-nowrap text-[10.5px]" style={{ color: "var(--ink-faint)" }}>
                Chủ đề:
              </span>
              <select
                value={conceptId ?? ""}
                onChange={(e) => setConceptId(e.target.value ? Number(e.target.value) : undefined)}
                className="flex-1 bg-transparent text-[11px] focus:outline-none"
                style={{ color: "var(--ink-soft)" }}
              >
                <option value="">Tự nhận diện</option>
                {concepts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              {conceptId === undefined && detectedConceptId !== null && (
                <span
                  className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold"
                  style={{ background: "var(--accent-bg)", color: "var(--accent-ink)" }}
                  title="Hệ thống nhận diện chủ đề này từ câu hỏi của bạn - chọn lại ở ô bên trái nếu không đúng"
                >
                  {concepts.find((c) => c.id === detectedConceptId)?.name ?? "?"}
                </span>
              )}
            </div>
          )}

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
