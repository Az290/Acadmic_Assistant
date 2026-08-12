"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  ChunkDetail,
  CitationPublic,
  ConceptPublic,
  CoursePublic,
  streamChat,
} from "@/lib/api";
import NovaAvatar from "@/components/NovaAvatar";

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
  // Trạng thái xử lý hiện tại - hiện thay cho bong bóng rỗng trong ~2
  // giây trước khi có chữ đầu tiên. Xoá đi ngay khi chữ bắt đầu về.
  status?: "checking" | "searching" | "generating";
  // Số đoạn tài liệu tìm được (đi kèm status "generating")
  sourcesFound?: number;
  // messageId: id trong database - có sau khi stream xong, dùng để gửi
  // đánh giá 👍/👎. Tin nhắn đang stream chưa có id nên chưa đánh giá được.
  messageId?: number;
  // Độ khớp tài liệu (0-1): mức tương đồng ngữ nghĩa của đoạn tài liệu
  // khớp nhất với câu hỏi. KHÔNG PHẢI "xác suất trả lời đúng" - xem
  // app/db/models.py::Message.retrieval_similarity ở backend.
  retrievalSimilarity?: number | null;
  // Đánh giá của chính người dùng cho câu trả lời này (undefined = chưa đánh giá).
  feedback?: boolean;
}

interface TabState {
  messages: DisplayMessage[];
  conversationId: number | undefined;
}

/**
 * Chữ mô tả từng bước xử lý - viết cho người học đọc, KHÔNG dùng thuật
 * ngữ kỹ thuật (không nói "guardrail", "embedding", "retrieval").
 *
 * Bước cuối kèm số đoạn tài liệu tìm được: người dùng thấy ngay hệ
 * thống có căn cứ thật, hoặc biết trước là không tìm thấy gì thay vì
 * bất ngờ khi đọc câu trả lời "tôi không có đủ thông tin".
 */
function STATUS_LABEL(stage: "checking" | "searching" | "generating", sourcesFound?: number): string {
  if (stage === "checking") return "Nova đang đọc câu hỏi…";
  if (stage === "searching") return "Nova đang tìm trong tài liệu…";
  if (sourcesFound === 0) return "Không tìm thấy tài liệu phù hợp, Nova đang soạn câu trả lời…";
  return `Đã tìm thấy ${sourcesFound} đoạn tài liệu, Nova đang soạn câu trả lời…`;
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
  // Đoạn tài liệu đang xem chi tiết (bấm vào badge trích dẫn) - null
  // nghĩa là không mở modal nào.
  const [viewingChunk, setViewingChunk] = useState<ChunkDetail | null>(null);
  const [chunkLoading, setChunkLoading] = useState<number | null>(null);
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
            if (event.type === "status") {
              messages[lastIndex] = {
                ...messages[lastIndex],
                status: event.stage,
                sourcesFound: event.sources_found,
              };
              return { ...prev, [activeTab]: { ...state, messages } };
            }
            if (event.type === "chunk") {
              messages[lastIndex] = {
                ...messages[lastIndex],
                content: messages[lastIndex].content + event.text,
                // Chữ đã bắt đầu về -> không cần báo tiến trình nữa
                status: undefined,
              };
              return { ...prev, [activeTab]: { ...state, messages } };
            }
            if (event.type === "done") {
              messages[lastIndex] = {
                ...messages[lastIndex],
                citations: event.citations,
                streaming: false,
                messageId: event.message_id,
                retrievalSimilarity: event.retrieval_similarity,
                // Phòng trường hợp không có chunk nào (câu trả lời rỗng)
                // - status vẫn phải biến mất khi đã xong.
                status: undefined,
              };
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

  /**
   * Mở đoạn tài liệu gốc mà AI đã trích dẫn - để người học tự kiểm
   * chứng câu trả lời thay vì phải tin tuyệt đối vào AI.
   *
   * Backend áp dụng đúng bộ lọc quyền của tìm kiếm (xem
   * app/retrieval/access_policy.py) nên không lo lộ nội dung lớp khác.
   */
  async function openChunk(chunkId: number) {
    setChunkLoading(chunkId);
    try {
      const detail = await api.get<ChunkDetail>(`/v1/chunks/${chunkId}`);
      setViewingChunk(detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không mở được đoạn tài liệu.");
    } finally {
      setChunkLoading(null);
    }
  }

  /**
   * Gửi đánh giá 👍/👎 cho 1 câu trả lời. Cập nhật giao diện NGAY
   * (optimistic) rồi mới gọi API - thao tác này nhỏ, phản hồi tức thì
   * quan trọng hơn việc chờ xác nhận từ server. Nếu API lỗi, trả lại
   * trạng thái cũ để không hiển thị sai sự thật.
   */
  async function sendFeedback(messageId: number, isPositive: boolean) {
    const applyFeedback = (value: boolean | undefined) =>
      setTabs((prev) => {
        const next = { ...prev };
        (Object.keys(next) as TabMode[]).forEach((t) => {
          next[t] = {
            ...next[t],
            messages: next[t].messages.map((m) =>
              m.messageId === messageId ? { ...m, feedback: value } : m
            ),
          };
        });
        return next;
      });

    applyFeedback(isPositive);
    try {
      await api.post(`/v1/messages/${messageId}/feedback`, { is_positive: isPositive });
    } catch {
      applyFeedback(undefined);
    }
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

  // Mở panel ở 1 tab cụ thể mà KHÔNG chỉ định khái niệm - phát ra từ
  // các thẻ điều hướng ở trang chủ sinh viên. Khác "open-tutor-chat"
  // (luôn kèm courseId + conceptId từ Proactive Toast) nên tách sự kiện
  // riêng thay vì nhồi tham số tuỳ chọn vào cùng 1 sự kiện.
  useEffect(() => {
    function handleOpenChatTab(e: Event) {
      const detail = (e as CustomEvent<{ tab: TabMode }>).detail;
      setTab(detail.tab);
      setSize((prev) => (prev === "closed" ? "compact" : prev));
      setUnreadCount(0);
    }
    window.addEventListener("open-chat-tab", handleOpenChatTab);
    return () => window.removeEventListener("open-chat-tab", handleOpenChatTab);
  }, []);

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
      {isOpen && (
        <div
          className={`animate-fade flex flex-col overflow-hidden rounded-[12px] border ${PANEL_SIZE_CLASS[size]}`}
          style={{
            background: "#ffffff",
            borderColor: "var(--border-strong)",
            // Bóng đổ nhẹ và khuếch tán rộng - đủ để panel tách khỏi nền
            // mà không có viền tối đậm kiểu hộp thoại cảnh báo.
            boxShadow: "0 8px 32px rgba(15, 23, 42, 0.14)",
          }}
        >
          {/* Header: Nova + nút đổi cỡ + nút đóng */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ background: "var(--sidebar)" }}
          >
            <div className="flex items-center gap-2.5">
              <NovaAvatar size={26} />
              <div className="leading-tight">
                <div className="text-[13px] font-semibold text-white">Nova</div>
                <div className="text-[10.5px]" style={{ color: "var(--sidebar-ink)" }}>
                  Trợ lý học thuật
                </div>
              </div>
            </div>
            <div className="flex items-center gap-0.5">
              {(["compact", "half", "full"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSize(s)}
                  className="rounded-[4px] px-1.5 py-0.5 text-[10px] font-medium"
                  style={{
                    color: size === s ? "#ffffff" : "var(--sidebar-ink)",
                    background: size === s ? "var(--sidebar-active)" : "transparent",
                    transition: "background-color var(--motion-fast) var(--ease)",
                  }}
                  title={s === "compact" ? "Thu nhỏ" : s === "half" ? "Vừa" : "Phóng to"}
                >
                  {s === "compact" ? "S" : s === "half" ? "M" : "L"}
                </button>
              ))}
              <button
                onClick={() => setSize("closed")}
                className="ml-1 rounded-[4px] px-1.5 py-0.5 text-[13px] leading-none"
                style={{ color: "var(--sidebar-ink)", transition: "color var(--motion-fast) var(--ease)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "#fff")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--sidebar-ink)")}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Tabs: Hỏi đáp / Gia sư */}
          <div className="flex border-b" style={{ borderColor: "var(--border)" }}>
            {(["RAG_QUESTION", "SOCRATIC_REQUEST"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="flex-1 py-2.5 text-[12.5px] font-medium"
                style={{
                  color: tab === t ? "var(--ink)" : "var(--ink-faint)",
                  fontWeight: tab === t ? 600 : 400,
                  borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
                  transition: "color var(--motion-fast) var(--ease), border-color var(--motion-fast) var(--ease)",
                }}
              >
                {TAB_LABEL[t]}
              </button>
            ))}
          </div>

          {/* Chọn lớp đang hỏi - để trống thì hệ thống tự nhận diện */}
          {courses.length > 0 && (
            <div className="border-b px-3 py-1.5" style={{ borderColor: "var(--border)", background: "var(--panel-soft)" }}>
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
              style={{ borderColor: "var(--border)", background: "var(--panel-soft)" }}
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
              <div className="flex flex-col items-center gap-2.5 pt-6 text-center">
                <NovaAvatar size={38} />
                <p className="text-support max-w-[260px]">
                  {tab === "RAG_QUESTION"
                    ? "Hỏi Nova về nội dung môn học — mỗi câu trả lời đều kèm trích dẫn để bạn tự kiểm chứng."
                    : "Chế độ Gia sư: Nova gợi mở từng bước để bạn tự tìm ra đáp án, thay vì đưa lời giải ngay."}
                </p>
              </div>
            )}

            {current.messages.map((m, i) => (
              <div key={i} className={`animate-fade flex gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {/* Avatar chỉ ở tin nhắn của Nova - tin nhắn người dùng
                    không cần avatar (họ biết mình là ai), thêm vào chỉ
                    làm chật khung chat vốn đã hẹp. */}
                {m.role === "assistant" && !m.blocked && (
                  <div className="mt-0.5">
                    <NovaAvatar size={22} />
                  </div>
                )}
                <div
                  className={`max-w-[82%] rounded-[10px] px-3 py-2 text-[12.5px] leading-relaxed ${
                    m.role === "user" ? "text-white" : ""
                  }`}
                  style={
                    m.role === "user"
                      ? { background: "var(--accent)" }
                      : m.blocked
                        ? { background: "var(--red-bg)", border: "1px solid #f0d0d0", color: "var(--red-ink)" }
                        : { background: "var(--panel-soft)", border: "1px solid var(--border)", color: "var(--ink)" }
                  }
                >
                  {/* Trạng thái xử lý - hiện THAY CHO bong bóng rỗng
                      trong ~2 giây trước khi có chữ đầu tiên, để người
                      dùng biết hệ thống đang làm gì thay vì tưởng treo. */}
                  {m.status && (
                    <div className="flex items-center gap-1.5 text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
                      <span className="flex gap-[3px]">
                        <span className="h-[5px] w-[5px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:0ms]" />
                        <span className="h-[5px] w-[5px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:150ms]" />
                        <span className="h-[5px] w-[5px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:300ms]" />
                      </span>
                      <span>{STATUS_LABEL(m.status, m.sourcesFound)}</span>
                    </div>
                  )}

                  {/* Ẩn hẳn khối nội dung khi đang hiện trạng thái mà
                      chưa có chữ nào - tránh khoảng trống thừa dưới dòng
                      trạng thái. */}
                  <div className={`whitespace-pre-wrap ${m.status && !m.content ? "hidden" : ""}`}>
                    {m.content}
                    {m.streaming && !m.status && <span className="animate-pulse">▍</span>}
                  </div>

                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {m.citations.map((c) => (
                        <button
                          key={c.chunk_id}
                          onClick={() => openChunk(c.chunk_id)}
                          disabled={chunkLoading === c.chunk_id}
                          className="rounded bg-blue-50 px-1.5 py-0.5 text-[9px] font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
                          title={`Bấm để xem nguyên văn đoạn này${c.page_number ? ` (trang ${c.page_number})` : ""}`}
                        >
                          {chunkLoading === c.chunk_id ? "…" : `#${c.chunk_id}`}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Đánh giá + độ khớp tài liệu - chỉ hiện với câu trả
                      lời ĐÃ stream xong (có messageId), không hiện với
                      tin nhắn bị chặn hoặc câu hỏi của chính người dùng. */}
                  {m.role === "assistant" && !m.blocked && m.messageId !== undefined && (
                    <div className="mt-1.5 flex items-center gap-1.5 border-t border-[color:var(--border)] pt-1.5">
                      <button
                        onClick={() => sendFeedback(m.messageId!, true)}
                        className="rounded px-1 text-[13px] leading-none transition-opacity"
                        style={{ opacity: m.feedback === true ? 1 : 0.35 }}
                        title="Câu trả lời này hữu ích"
                        aria-label="Hữu ích"
                      >
                        👍
                      </button>
                      <button
                        onClick={() => sendFeedback(m.messageId!, false)}
                        className="rounded px-1 text-[13px] leading-none transition-opacity"
                        style={{ opacity: m.feedback === false ? 1 : 0.35 }}
                        title="Câu trả lời này chưa hữu ích"
                        aria-label="Chưa hữu ích"
                      >
                        👎
                      </button>
                      {m.retrievalSimilarity !== null && m.retrievalSimilarity !== undefined && (
                        <span
                          className="ml-auto text-[9.5px]"
                          style={{ color: "var(--ink-faint)" }}
                          title={`Độ tương đồng ngữ nghĩa của đoạn tài liệu khớp nhất: ${m.retrievalSimilarity.toFixed(3)}. Đây KHÔNG phải xác suất câu trả lời đúng.`}
                        >
                          Độ khớp tài liệu: {(m.retrievalSimilarity * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={scrollRef} />
          </div>

          {error && <p className="px-3 pb-1 text-[11px] text-red-600">{error}</p>}

          {/* Ô nhập */}
          <div className="flex gap-2 border-t p-2.5" style={{ borderColor: "var(--border)" }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Hỏi Nova…"
              className="flex-1 rounded-[6px] border px-3 py-2 text-[12.5px] focus:outline-none"
              style={{ borderColor: "var(--border-strong)", transition: "border-color var(--motion-fast) var(--ease)" }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent-strong)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="btn btn-primary"
            >
              Gửi
            </button>
          </div>
        </div>
      )}

      {/* Modal xem nguyên văn đoạn trích dẫn - để người học tự kiểm
          chứng câu trả lời, không phải tin tuyệt đối vào AI. */}
      {viewingChunk && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          style={{ background: "rgba(10, 12, 30, 0.45)" }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setViewingChunk(null);
          }}
        >
          <div
            className="max-h-[80vh] w-[560px] max-w-[92vw] overflow-y-auto rounded-xl border bg-white p-5"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="text-[13px] font-bold">Nguồn trích dẫn</div>
                <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                  {viewingChunk.document_title}
                  {viewingChunk.page_number !== null && ` · trang ${viewingChunk.page_number}`}
                </div>
              </div>
              <button
                onClick={() => setViewingChunk(null)}
                className="text-[16px] leading-none"
                style={{ color: "var(--ink-faint)" }}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>
            <div
              className="whitespace-pre-wrap rounded-[9px] border p-3 text-[12.5px] leading-relaxed"
              style={{ background: "var(--panel-soft)", borderColor: "var(--border)", color: "var(--ink)" }}
            >
              {viewingChunk.content}
            </div>
          </div>
        </div>
      )}

      {/* Bong bóng tròn - luôn hiện, badge số đỏ khi có tin nhắn chưa xem */}
      <button
        onClick={isOpen ? () => setSize("closed") : openPanel}
        className="relative flex h-[52px] w-[52px] items-center justify-center rounded-full"
        style={{
          background: "var(--accent)",
          boxShadow: "0 4px 16px rgba(30, 58, 95, 0.32)",
          transition: "background-color var(--motion-fast) var(--ease)",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "#16304f")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "var(--accent)")}
        aria-label={isOpen ? "Đóng Nova" : "Mở Nova - trợ lý học thuật"}
      >
        {/* Biểu tượng Nova thay cho bong bóng chat mặc định - người dùng
            nhận ra "đây là Nova" chứ không phải "đây là ô chat chung
            chung". Không phóng to khi rê chuột: hiệu ứng nảy gây cảm
            giác đồ chơi, không hợp môi trường học thuật. */}
        {isOpen ? (
          <span className="text-[18px] leading-none text-white">✕</span>
        ) : (
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#fff"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 2.5 Q13 9.5 21.5 12 Q13 14.5 12 21.5 Q11 14.5 2.5 12 Q11 9.5 12 2.5 Z" />
          </svg>
        )}
        {!isOpen && unreadCount > 0 && (
          <span
            className="absolute -right-0.5 -top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white"
            style={{ background: "var(--red)", border: "2px solid var(--bg)" }}
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>
    </div>
  );
}
