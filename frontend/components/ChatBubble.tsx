"use client";

import { useEffect, useRef, useState } from "react";
import {
  ActionResultPublic,
  api,
  ApiError,
  ChunkDetail,
  CitationPublic,
  ConceptPublic,
  ConversationSessionPublic,
  ConversationSummary,
  CoursePublic,
  getConversationSummary,
  getSuggestedQuestions,
  MessagePublic,
  PendingActionPublic,
  streamChat,
} from "@/lib/api";
import NovaAvatar from "@/components/NovaAvatar";
import VoiceInput from "@/components/VoiceInput";
import { useAuth } from "@/lib/AuthContext";

function speakNovaResponse(text: string) {
  if (!("speechSynthesis" in window)) return;
  const spokenText = text
    .replace(/```[\s\S]*?```/g, " đoạn mã ")
    .replace(/[*_#>`~]/g, "")
    .replace(/\[([^\]]+)]\([^\)]+\)/g, "$1")
    .trim();
  if (!spokenText) return;

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(spokenText);
  utterance.lang = "vi-VN";
  utterance.rate = 1;
  const vietnameseVoice = window.speechSynthesis
    .getVoices()
    .find((voice) => voice.lang.toLowerCase().startsWith("vi"));
  if (vietnameseVoice) utterance.voice = vietnameseVoice;
  window.speechSynthesis.speak(utterance);
}

/**
 * ChatBubble - panel chat nổi kiểu Messenger, hiện ở MỌI trang (được
 * đặt trong DashboardLayout, ngoài <main>) thay vì là 1 trang /chat
 * riêng biệt - đúng theo yêu cầu prototype: người dùng không cần rời
 * trang đang xem để hỏi, và có thể thu nhỏ lại khi không cần.
 *
 * Chế độ "Hỏi đáp" để Router tự phân loại; "Gia sư" ép SOCRATIC_REQUEST.
 * gửi kèm mỗi request - mỗi tab giữ conversation_id RIÊNG (2 phiên
 * hội thoại độc lập), tránh trộn lẫn lịch sử giữa 2 kiểu trả lời khác
 * hẳn nhau (RAG_QUESTION trả lời thẳng vs SOCRATIC_REQUEST gợi mở).
 */

type PanelSize = "closed" | "compact" | "full";
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
  // Hành động Nova ĐỀ XUẤT, đang chờ xác nhận (category "ACTION_REQUEST").
  // ĐÃ đọc kỹ backend (agent.py::handle_chat_stream) để xác nhận: khi có
  // pendingAction/actionResult thì KHÔNG có "chunk" nào đi kèm trong
  // cùng lượt đó (2 loại sự kiện LOẠI TRỪ NHAU) - content ở đây sẽ RỖNG,
  // nên UI card phải tự hiển thị đủ text (arguments_summary/summary),
  // không thể trông chờ content đã có sẵn câu văn tương ứng.
  pendingAction?: PendingActionPublic;
  actionResult?: ActionResultPublic;
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

// Người dùng chỉ cần hai trạng thái rõ ràng: cửa sổ chat mặc định và mở rộng.
// max-width/max-height giữ panel an toàn trên màn hình nhỏ.
const PANEL_SIZE_CLASS: Record<Exclude<PanelSize, "closed">, string> = {
  compact: "h-[min(650px,calc(100vh-40px))] w-[min(450px,calc(100vw-40px))]",
  full: "h-[calc(100vh-40px)] w-[min(720px,calc(100vw-40px))]",
};

function emptyTabState(): TabState {
  return { messages: [], conversationId: undefined };
}

// Key localStorage lưu conversationId theo TỪNG tab riêng biệt - Hỏi
// đáp và Gia sư là 2 phiên hội thoại độc lập (xem comment đầu file),
// nên phải tách key để F5 không làm trộn lẫn conversationId của 2 tab.
function conversationStorageKey(tabMode: TabMode): string {
  return `nova-conversation-${tabMode}`;
}

/**
 * Đọc conversationId đã lưu từ lần trước - BỌC try/catch vì
 * localStorage có thể ném lỗi ở private mode / trình duyệt chặn
 * storage (Safari private browsing là ví dụ điển hình). Lỗi thì coi
 * như chưa có gì lưu, không phải bug nghiêm trọng cần báo người dùng.
 */
function readStoredConversationId(tabMode: TabMode): number | undefined {
  void tabMode;
  // Không tự khôi phục phiên cũ khi đăng nhập/mở lại ứng dụng. Người dùng chỉ
  // quay lại phiên cũ bằng thao tác chọn rõ ràng trong danh sách lịch sử.
  return undefined;
}

interface NovaPreference {
  preferred_language: "auto" | "vi" | "en";
  explanation_depth: "auto" | "beginner" | "intermediate" | "advanced";
  response_length: "auto" | "short" | "medium" | "detailed";
  example_style: "auto" | "code" | "analogy" | "step_by_step";
}

interface NovaMemory {
  conversation_id: number;
  summary: string;
  updated_at: string | null;
}

const DEFAULT_NOVA_PREFERENCE: NovaPreference = {
  preferred_language: "auto",
  explanation_depth: "auto",
  response_length: "auto",
  example_style: "auto",
};

function writeStoredConversationId(tabMode: TabMode, conversationId: number | undefined): void {
  try {
    if (conversationId === undefined) {
      localStorage.removeItem(conversationStorageKey(tabMode));
    } else {
      localStorage.setItem(conversationStorageKey(tabMode), String(conversationId));
    }
  } catch {
    // localStorage không khả dụng (private mode, v.v.) - bỏ qua, không
    // ảnh hưởng chức năng chat trong phiên hiện tại.
  }
}

/** Chuyển MessagePublic (từ API lịch sử) sang DisplayMessage (state của ChatBubble). */
function toDisplayMessage(m: MessagePublic): DisplayMessage {
  return {
    role: m.role,
    content: m.content,
    citations: m.citations,
    messageId: m.message_id,
    retrievalSimilarity: m.retrieval_similarity,
    // pending_action null -> giữ undefined (khớp kiểu optional của
    // DisplayMessage) - backend CHỈ set khác null ở tin nhắn assistant
    // CUỐI CÙNG nếu đang có hành động chờ xác nhận (xem MessagePublic).
    pendingAction: m.pending_action ?? undefined,
  };
}

export default function ChatBubble() {
  const { user } = useAuth();
  const [size, setSize] = useState<PanelSize>("closed");
  const [tab, setTab] = useState<TabMode>("RAG_QUESTION");
  // Khởi tạo conversationId từ localStorage NGAY TỪ ĐẦU (đọc string thì
  // đồng bộ, không cần useEffect) - messages thì phải đợi useEffect gọi
  // API để "hydrate" (xem effect bên dưới) vì đó là thao tác async.
  const [tabs, setTabs] = useState<Record<TabMode, TabState>>({
    RAG_QUESTION: emptyTabState(),
    SOCRATIC_REQUEST: emptyTabState(),
  });
  // Tab nào đang hiện dòng "Tiếp tục cuộc trò chuyện trước" - chỉ bật
  // sau khi hydrate THÀNH CÔNG (có lịch sử thật từ server), tắt ngay
  // nếu người dùng gửi tin nhắn mới hoặc bắt đầu hội thoại mới.
  const [hydratedTabs, setHydratedTabs] = useState<Partial<Record<TabMode, boolean>>>({});
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
  // Menu chọn nguồn tham khảo - lưu ĐÚNG object DisplayMessage đang mở
  // menu (không phải id) vì message không có id ổn định khi đang stream;
  // null nghĩa là không có menu nào đang mở.
  const [openCitationMenuFor, setOpenCitationMenuFor] = useState<DisplayMessage | null>(null);
  // Suggested questions: câu hỏi gợi ý sau khi Nova trả lời xong
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  // Summary: tóm tắt cuộc trò chuyện - hiện khi có 10+ tin nhắn
  const [showSummary, setShowSummary] = useState(false);
  const [summaryData, setSummaryData] = useState<ConversationSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  // Đổi label nút "Sao chép" tạm thời để báo kết quả - null nghĩa là
  // trạng thái bình thường (chưa bấm hoặc đã hết thời gian hiện thông báo).
  const [copyStatus, setCopyStatus] = useState<"success" | "error" | null>(null);
  const [showSessions, setShowSessions] = useState(false);
  const [sessions, setSessions] = useState<ConversationSessionPublic[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [showPreferences, setShowPreferences] = useState(false);
  const [preferences, setPreferences] = useState<NovaPreference>(DEFAULT_NOVA_PREFERENCE);
  const [preferencesLoading, setPreferencesLoading] = useState(false);
  const [preferencesSaving, setPreferencesSaving] = useState(false);
  const [memories, setMemories] = useState<NovaMemory[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const isOpen = size !== "closed";
  const current = tabs[tab];
  const sendRef = useRef(handleSend);
  const selectedCourse = courses.find((course) => course.id === courseId);
  const isInstructorContext =
    user?.role === "ADMIN" ||
    (user?.role === "INSTRUCTOR" && (courseId === undefined || selectedCourse?.owner_id === user.id));

  async function openPreferences() {
    setShowPreferences(true);
    setPreferencesLoading(true);
    try {
      const [loadedPreferences, loadedMemories] = await Promise.all([
        api.get<NovaPreference>("/v1/nova/preferences/me"),
        api.get<NovaMemory[]>("/v1/nova/memory/me"),
      ]);
      setPreferences(loadedPreferences);
      setMemories(loadedMemories);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Không thể tải tùy chọn của Nova.");
    } finally {
      setPreferencesLoading(false);
    }
  }

  async function savePreferences() {
    setPreferencesSaving(true);
    try {
      setPreferences(await api.patch<NovaPreference>("/v1/nova/preferences/me", preferences));
      setShowPreferences(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Không thể lưu tùy chọn của Nova.");
    } finally {
      setPreferencesSaving(false);
    }
  }

  async function resetPreferences() {
    setPreferencesSaving(true);
    try {
      await api.delete<void>("/v1/nova/preferences/me");
      setPreferences(DEFAULT_NOVA_PREFERENCE);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Không thể xóa tùy chọn của Nova.");
    } finally {
      setPreferencesSaving(false);
    }
  }

  async function clearConversationMemory() {
    setPreferencesSaving(true);
    try {
      await api.delete<{ deleted: number }>("/v1/nova/memory/me");
      setMemories([]);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Không thể xóa bộ nhớ hội thoại.");
    } finally {
      setPreferencesSaving(false);
    }
  }

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [tabs, tab]);

  useEffect(() => {
    if (!user?.id) {
      setCourses([]);
      return;
    }
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then(setCourses)
      .catch(() => setCourses([]));
  }, [user?.id]);

  // Hydrate lại messages của từng tab từ conversationId đã lưu ở
  // localStorage (đọc lúc khởi tạo state ở trên) - CHỈ chạy 1 lần khi
  // mount, không phụ thuộc `tab` hiện tại để tránh gọi lại API mỗi khi
  // người dùng chuyển qua lại 2 tab.
  useEffect(() => {
    (["RAG_QUESTION", "SOCRATIC_REQUEST"] as TabMode[]).forEach((tabMode) => {
      const convId = readStoredConversationId(tabMode);
      if (convId === undefined) return;

      api
        .get<MessagePublic[]>(`/v1/chat/${convId}/messages`)
        .then((history) => {
          setTabs((prev) => ({
            ...prev,
            [tabMode]: { conversationId: convId, messages: history.map(toDisplayMessage) },
          }));
          setHydratedTabs((prev) => ({ ...prev, [tabMode]: true }));
        })
        .catch((err) => {
          // 404: conversation không còn tồn tại hoặc không thuộc user
          // hiện tại (vd. đăng xuất rồi đăng nhập tài khoản khác) - đây
          // là trường hợp BÌNH THƯỜNG, không phải lỗi cần báo người
          // dùng. Dọn key cũ và coi tab đó như chưa từng có hội thoại.
          if (err instanceof ApiError && err.status === 404) {
            writeStoredConversationId(tabMode, undefined);
            setTabs((prev) => ({ ...prev, [tabMode]: emptyTabState() }));
          }
          // Lỗi khác (mất mạng, server lỗi...) - giữ nguyên conversationId
          // đã đọc, để lần mở panel sau vẫn còn cơ hội thử lại; chỉ là
          // messages sẽ trống cho tới khi người dùng gửi tin nhắn mới.
        });
    });
  }, []);

  // Danh sách khái niệm chỉ có ý nghĩa khi đã chọn 1 lớp cụ thể - mỗi
  // lớp có bộ khái niệm riêng do giảng viên lớp đó tạo.
  useEffect(() => {
    // Reset nguyên tử state phụ thuộc khi người dùng chủ động đổi lớp.
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

  // Xoá gợi ý khi bắt đầu gửi câu hỏi mới
  function clearSuggestedQuestions() {
    setSuggestedQuestions([]);
    setOpenCitationMenuFor(null);
  }

  // Tóm tắt cuộc trò chuyện
  async function handleSummarize() {
    const convId = current.conversationId;
    if (!convId) return;

    setShowSummary(true);
    setSummaryLoading(true);
    setSummaryData(null);

    try {
      const data = await getConversationSummary(convId);
      setSummaryData(data);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : "Không thể tải tóm tắt";
      setError(message);
      setShowSummary(false);
    } finally {
      setSummaryLoading(false);
    }
  }

  // Bắt đầu cuộc trò chuyện mới
  function handleStartNewConversation() {
    updateCurrentTab(() => ({ messages: [], conversationId: undefined }));
    writeStoredConversationId(tab, undefined); // xoá key cũ - không để sót conversationId đã kết thúc
    setHydratedTabs((prev) => ({ ...prev, [tab]: false }));
    setShowSummary(false);
    setSummaryData(null);
    setSuggestedQuestions([]);
    clearSuggestedQuestions();
    setShowSessions(false);
  }

  async function openSessionList() {
    setShowSessions(true);
    setSessionsLoading(true);
    setError(null);
    try {
      setSessions(await api.get<ConversationSessionPublic[]>("/v1/chat/conversations"));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không thể tải danh sách phiên trò chuyện.");
    } finally {
      setSessionsLoading(false);
    }
  }

  async function openConversationSession(sessionItem: ConversationSessionPublic) {
    setSessionsLoading(true);
    setError(null);
    try {
      const history = await api.get<MessagePublic[]>(`/v1/chat/${sessionItem.conversation_id}/messages`);
      setTabs((prev) => ({
        ...prev,
        [tab]: {
          conversationId: sessionItem.conversation_id,
          messages: history.map(toDisplayMessage),
        },
      }));
      writeStoredConversationId(tab, sessionItem.conversation_id);
      setCourseId(sessionItem.course_id ?? undefined);
      setHydratedTabs((prev) => ({ ...prev, [tab]: true }));
      setShowSessions(false);
      setSuggestedQuestions([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không thể mở phiên trò chuyện này.");
    } finally {
      setSessionsLoading(false);
    }
  }

  // Copy summary vào clipboard
  function copySummary() {
    if (!summaryData) return;
    const text = `${summaryData.summary}\n\nĐiểm chính:\n${summaryData.key_points.map((p, i) => `${i + 1}. ${p}`).join("\n")}`;
    navigator.clipboard
      .writeText(text)
      .then(() => setCopyStatus("success"))
      .catch(() => {
        // Trình duyệt chặn quyền clipboard (thường gặp ở permission
        // policy nghiêm ngặt/không phải HTTPS) - báo cho người dùng biết
        // thay vì im lặng, để họ tự chọn văn bản thủ công nếu cần.
        setCopyStatus("error");
      });
    // Tự tắt thông báo sau 2s - không cần người dùng bấm gì thêm.
    setTimeout(() => setCopyStatus(null), 2000);
  }

  // overrideText: dùng khi gửi tin nhắn KHÔNG qua ô nhập liệu (vd nút
  // "Xác nhận"/"Huỷ" của thẻ pendingAction) - setInput() rồi gọi thẳng
  // handleSend() trong cùng lượt sự kiện sẽ đọc phải `input` CŨ (closure
  // chưa thấy state vừa cập nhật), nên phải truyền thẳng text cần gửi
  // thay vì trông chờ state kịp đổi.
  async function handleSend(overrideText?: string, voiceMode = false) {
    const text = (overrideText ?? input).trim();
    if (!text) return;
    if (sending) {
      if (voiceMode) {
        window.dispatchEvent(
          new CustomEvent("nova-voice-error", {
            detail: { message: "Nova đang xử lý một yêu cầu khác. Bạn hãy gọi lại sau khi Nova trả lời xong." },
          })
        );
      }
      return;
    }

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
    clearSuggestedQuestions();
    let voiceAnswer = "";

    try {
      await streamChat(
        {
          message: text,
          conversation_id: tabs[activeTab].conversationId,
          course_id: courseId,
          // "Hỏi đáp" có thể là kiến thức lớp, kiến thức phổ thông, chitchat,
          // câu hỏi hệ thống hoặc yêu cầu thao tác. Không ép RAG_QUESTION ở đây,
          // nếu không Router sẽ không bao giờ nhìn thấy các loại câu hỏi đó.
          // Chỉ "Gia sư" là một ý định tường minh cần ép SOCRATIC_REQUEST.
          force_category:
            !isInstructorContext && activeTab === "SOCRATIC_REQUEST"
              ? "SOCRATIC_REQUEST"
              : undefined,
          // Chỉ gửi khi ở chế độ Gia sư - chế độ Hỏi đáp không dùng
          // khái niệm để điều chỉnh cách trả lời.
          concept_id: activeTab === "SOCRATIC_REQUEST" ? conceptId : undefined,
        },
        (event) => {
          if (voiceMode) {
            if (event.type === "chunk") voiceAnswer += event.text;
            if (event.type === "action_pending") {
              voiceAnswer = `${event.arguments_summary}. Hãy nói có để xác nhận hoặc không để huỷ.`;
            }
            if (event.type === "action_result") voiceAnswer = event.summary;
            if (event.type === "blocked") {
              voiceAnswer = "Câu hỏi của bạn không hợp lệ, vui lòng đặt câu hỏi khác.";
            }
          }
          setTabs((prev) => {
            const state = prev[activeTab];
            const messages = [...state.messages];
            const lastIndex = messages.length - 1;

            if (event.type === "start") {
              writeStoredConversationId(activeTab, event.conversation_id);
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
            if (event.type === "action_pending") {
              // Nova đề xuất 1 hành động GHI, đang chờ xác nhận. KHÔNG
              // có "chunk" nào đi kèm sự kiện này (đã đọc kỹ backend
              // agent.py::handle_chat_stream để xác nhận) nên content
              // giữ nguyên rỗng - text hiển thị lấy thẳng từ
              // arguments_summary trong thẻ xác nhận (xem JSX bên dưới).
              messages[lastIndex] = {
                ...messages[lastIndex],
                pendingAction: {
                  tool_name: event.tool_name,
                  tool_label_vi: event.tool_label_vi,
                  arguments_summary: event.arguments_summary,
                },
                status: undefined,
                streaming: false,
              };
              return { ...prev, [activeTab]: { ...state, messages } };
            }
            if (event.type === "action_result") {
              // Tương tự action_pending: KHÔNG có "chunk" đi kèm, content
              // vẫn rỗng - thẻ kết quả tự hiển thị summary.
              messages[lastIndex] = {
                ...messages[lastIndex],
                actionResult: {
                  tool_name: event.tool_name,
                  tool_label_vi: event.tool_label_vi,
                  success: event.success,
                  summary: event.summary,
                },
                status: undefined,
                streaming: false,
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
              const nextConversationId = event.conversation_id || state.conversationId;
              writeStoredConversationId(activeTab, nextConversationId);
              return {
                ...prev,
                [activeTab]: { messages, conversationId: nextConversationId },
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
      if (voiceMode) {
        window.dispatchEvent(
          new CustomEvent("nova-voice-response", {
            detail: { text: voiceAnswer || "Nova đã xử lý xong nhưng chưa nhận được nội dung trả lời." },
          })
        );
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : "Không thể gửi câu hỏi, vui lòng thử lại.";
      setError(message);
      if (voiceMode) {
        window.dispatchEvent(new CustomEvent("nova-voice-error", { detail: { message } }));
      }
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
    } catch (err) {
      // Revert lại icon về trạng thái CHƯA đánh giá - giữ nguyên logic
      // optimistic-update đã có, chỉ thêm phần BÁO CHO NGƯỜI DÙNG BIẾT
      // (trước đây im lặng hoàn toàn, người dùng thấy icon tự nhảy lại
      // mà không hiểu vì sao, tưởng UI bị lỗi).
      applyFeedback(undefined);
      setError(err instanceof ApiError ? err.detail : "Không gửi được đánh giá, vui lòng thử lại.");
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

  // Chế độ giao tiếp giọng nói gửi câu hỏi qua event và không mở panel.
  // Tái sử dụng nguyên luồng chat/guardrail/context hiện có thay vì tạo
  // một API bí mật riêng cho voice.
  useEffect(() => {
    function handleVoiceQuery(event: Event) {
      const detail = (event as CustomEvent<{ text: string }>).detail;
      if (!detail?.text.trim()) return;
      void sendRef.current(detail.text, true);
    }
    window.addEventListener("nova-voice-query", handleVoiceQuery);
    return () => window.removeEventListener("nova-voice-query", handleVoiceQuery);
  }, []);

  // Chỉ đọc thành tiếng câu trả lời phát sinh từ nút microphone trong khung chat.
  useEffect(() => {
    function handleVoiceResponse(event: Event) {
      const detail = (event as CustomEvent<{ text: string }>).detail;
      if (detail?.text) speakNovaResponse(detail.text);
    }
    function handleVoiceError(event: Event) {
      const detail = (event as CustomEvent<{ message: string }>).detail;
      if (detail?.message) speakNovaResponse(detail.message);
    }
    window.addEventListener("nova-voice-response", handleVoiceResponse);
    window.addEventListener("nova-voice-error", handleVoiceError);
    return () => {
      window.removeEventListener("nova-voice-response", handleVoiceResponse);
      window.removeEventListener("nova-voice-error", handleVoiceError);
      window.speechSynthesis?.cancel();
    };
  }, []);

  // Mở panel VÀ GỬI LUÔN 1 câu hỏi có sẵn - phát ra từ nút "Hỏi Nova
  // giải thích" ở trang quiz (kèm nguyên văn câu hỏi + đáp án sinh viên
  // chọn + đáp án đúng, để Nova giải thích ĐÚNG câu đó thay vì phải
  // hỏi lại "bạn đang nói câu nào?").
  //
  // Dùng ref cho handleSend: hàm này được tạo lại mỗi lần render, nếu
  // đưa vào deps thì listener bị gỡ/gắn liên tục; nếu để deps rỗng mà
  // gọi thẳng thì lại bắt phải closure cũ (state tabs/courseId lỗi thời).
  // Cập nhật ref trong effect, KHÔNG gán thẳng trong thân render: React
  // 19 coi việc ghi ref lúc render là tác dụng phụ không hợp lệ (render
  // phải thuần khiết để có thể bị huỷ/chạy lại an toàn).
  useEffect(() => {
    sendRef.current = handleSend;
  });

  useEffect(() => {
    function handleAskNova(e: Event) {
      const detail = (e as CustomEvent<{ question: string; tab?: TabMode }>).detail;
      setTab(detail.tab ?? "RAG_QUESTION");
      setSize((prev) => (prev === "closed" ? "compact" : prev));
      setUnreadCount(0);
      // Đợi 1 nhịp để setTab kịp áp dụng trước khi gửi - handleSend đọc
      // `tab` để quyết định gửi vào phiên hội thoại nào.
      setTimeout(() => sendRef.current(detail.question), 0);
    }
    window.addEventListener("ask-nova", handleAskNova);
    return () => window.removeEventListener("ask-nova", handleAskNova);
  }, []);

  // Fetch suggested questions khi conversation hoàn tất
  useEffect(() => {
    const convId = current.conversationId;
    if (!convId || current.messages.length === 0) return;

    // Chỉ fetch khi tin nhắn cuối cùng là của assistant và đã stream xong
    const lastMsg = current.messages[current.messages.length - 1];
    if (lastMsg?.role !== "assistant" || lastMsg.streaming || lastMsg.blocked) return;

    // setState ĐỒNG BỘ ngay trong effect gây "cascading render" (React
    // phải render lại trước khi kịp vẽ khung hình) - đẩy vào microtask
    // để lượt render hiện tại hoàn tất trước. `cancelled` chặn việc set
    // state sau khi component đã unmount hoặc hội thoại đã đổi, tránh
    // gợi ý của phiên cũ nhảy sang phiên mới.
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setSuggestionsLoading(true);
      getSuggestedQuestions(convId)
        .then((qs) => {
          if (!cancelled) setSuggestedQuestions(qs);
        })
        .catch(() => {
          if (!cancelled) setSuggestedQuestions([]);
        })
        .finally(() => {
          if (!cancelled) setSuggestionsLoading(false);
        });
    });
    return () => {
      cancelled = true;
    };
  // Chỉ chạy lại khi số lượng tin nhắn/phiên đổi; phụ thuộc cả mảng sẽ
  // gọi lại sau các cập nhật trạng thái streaming của cùng một tin.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.messages.length, current.conversationId]);

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
      {isOpen && (
        <div
          className={`animate-fade relative flex flex-col overflow-hidden rounded-2xl border ${PANEL_SIZE_CLASS[size]}`}
          style={{
            background: "#ffffff",
            borderColor: "var(--border-strong)",
            // Bóng đổ nhẹ và khuếch tán rộng - đủ để panel tách khỏi nền
            // mà không có viền tối đậm kiểu hộp thoại cảnh báo.
            boxShadow: "0 18px 48px rgba(15, 38, 70, 0.2)",
          }}
        >
          {/* Header chỉ có một điều khiển kích thước và một nút đóng. */}
          <div
            className="flex min-h-[68px] items-center justify-between px-4 py-3"
            style={{ background: "linear-gradient(135deg, #2469c7 0%, #164eaa 100%)" }}
          >
            <div className="flex items-center gap-2.5">
              <span className="flex h-11 w-11 items-center justify-center rounded-full border border-white/30 bg-white/12">
                <NovaAvatar size={38} />
              </span>
              <div className="leading-tight">
                <div className="text-[15px] font-bold text-white">Nova</div>
                <div className="mt-0.5 text-[11.5px] text-blue-100">
                  Trợ lý học thuật
                </div>
              </div>
            </div>
            {/* Nút Tóm tắt - hiện khi có 10+ tin nhắn */}
            {current.messages.length >= 10 && current.conversationId !== undefined && (
              <button
                onClick={handleSummarize}
                className="ml-2 flex items-center gap-1 rounded-[4px] px-2 py-1 text-[11px] font-medium transition-colors"
                style={{
                  background: "rgba(255,255,255,0.15)",
                  color: "#fff",
                }}
                title="Tóm tắt cuộc trò chuyện"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
                Tóm tắt
              </button>
            )}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleStartNewConversation}
                className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
                title="Phiên trò chuyện mới"
                aria-label="Bắt đầu phiên trò chuyện mới"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
              <button
                type="button"
                onClick={() => (showSessions ? setShowSessions(false) : void openSessionList())}
                className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
                title="Danh sách phiên trò chuyện"
                aria-label="Mở danh sách phiên trò chuyện"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v5h5" /><path d="M12 7v5l3 2" />
                </svg>
              </button>
              <button
                type="button"
                onClick={() => void openPreferences()}
                className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
                title="Cá nhân hóa Nova"
                aria-label="Mở tùy chọn cá nhân hóa Nova"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />
                </svg>
              </button>
              <button
                type="button"
                onClick={() => setSize(size === "full" ? "compact" : "full")}
                className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
                title={size === "full" ? "Thu nhỏ cửa sổ" : "Mở rộng cửa sổ"}
                aria-label={size === "full" ? "Thu nhỏ cửa sổ chat" : "Mở rộng cửa sổ chat"}
              >
                {size === "full" ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M8 3v5H3" /><path d="M16 21v-5h5" /><path d="m3 8 5-5" /><path d="m21 16-5 5" />
                  </svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M15 3h6v6" /><path d="M9 21H3v-6" /><path d="m21 3-7 7" /><path d="m3 21 7-7" />
                  </svg>
                )}
              </button>
              <button
                type="button"
                onClick={() => setSize("closed")}
                className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20"
                title="Đóng cửa sổ chat"
                aria-label="Đóng cửa sổ chat"
              >
                <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6 6 18" /><path d="m6 6 12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Sinh viên chọn Hỏi đáp/Gia sư; giảng viên dùng một chế độ
              trợ lý để Router có thể nhận diện cả yêu cầu gọi tool. */}
          {showSessions && (
            <div className="absolute inset-x-0 bottom-0 top-[68px] z-20 flex flex-col bg-white">
              <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
                <div>
                  <div className="text-[14px] font-bold" style={{ color: "var(--ink)" }}>Các phiên trò chuyện</div>
                  <div className="text-[11px]" style={{ color: "var(--ink-faint)" }}>Chỉ hiển thị lịch sử của tài khoản hiện tại</div>
                </div>
                <button type="button" onClick={() => setShowSessions(false)} className="rounded-lg px-3 py-1.5 text-[12px] font-semibold" style={{ color: "var(--accent)" }}>
                  Đóng
                </button>
              </div>
              <div className="flex-1 space-y-2 overflow-y-auto p-3">
                <button type="button" onClick={handleStartNewConversation} className="btn btn-primary w-full">
                  + Phiên trò chuyện mới
                </button>
                {sessionsLoading ? (
                  <p className="py-6 text-center text-[12px]" style={{ color: "var(--ink-faint)" }}>Đang tải lịch sử…</p>
                ) : sessions.length === 0 ? (
                  <p className="py-6 text-center text-[12px]" style={{ color: "var(--ink-faint)" }}>Chưa có phiên trò chuyện nào.</p>
                ) : sessions.map((sessionItem) => (
                  <button
                    key={sessionItem.conversation_id}
                    type="button"
                    onClick={() => void openConversationSession(sessionItem)}
                    className="w-full rounded-xl border p-3 text-left transition-colors hover:bg-slate-50"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <div className="truncate text-[12.5px] font-semibold" style={{ color: "var(--ink)" }}>{sessionItem.title}</div>
                    <div className="mt-1 flex justify-between text-[10.5px]" style={{ color: "var(--ink-faint)" }}>
                      <span>{sessionItem.message_count} tin nhắn</span>
                      <span>{new Date(sessionItem.updated_at).toLocaleString("vi-VN")}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="flex border-b" style={{ borderColor: "var(--border)" }}>
            {(isInstructorContext ? (["RAG_QUESTION"] as const) : (["RAG_QUESTION", "SOCRATIC_REQUEST"] as const)).map((t) => (
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
                {isInstructorContext ? "Trợ lý giảng dạy" : TAB_LABEL[t]}
              </button>
            ))}
          </div>

          {/* Chọn lớp đang hỏi - để trống thì hệ thống tự nhận diện */}
          {courses.length > 0 && (
            <div className="border-b px-3 py-1.5" style={{ borderColor: "var(--border)", background: "var(--panel-soft)" }}>
              <select
                value={courseId ?? ""}
                onChange={(e) => {
                  const nextCourseId = e.target.value ? Number(e.target.value) : undefined;
                  setCourseId(nextCourseId);
                  // Conversation đã gắn với một lớp thì không được tái sử
                  // dụng cho lớp khác; tạo phiên mới để role/context không
                  // bị trộn giữa hai lớp.
                  writeStoredConversationId("RAG_QUESTION", undefined);
                  writeStoredConversationId("SOCRATIC_REQUEST", undefined);
                  setTabs({
                    RAG_QUESTION: emptyTabState(),
                    SOCRATIC_REQUEST: emptyTabState(),
                  });
                  setHydratedTabs({});
                  const nextCourse = courses.find((course) => course.id === nextCourseId);
                  if (
                    user?.role === "ADMIN" ||
                    (user?.role === "INSTRUCTOR" && (nextCourseId === undefined || nextCourse?.owner_id === user.id))
                  ) {
                    setTab("RAG_QUESTION");
                  }
                }}
                className="w-full bg-transparent text-[11px] focus:outline-none"
                style={{ color: "var(--ink-soft)" }}
              >
                <option value="">Chọn lớp để cá nhân hóa</option>
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
          {!isInstructorContext && tab === "SOCRATIC_REQUEST" && concepts.length > 0 && (
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
                  {isInstructorContext
                    ? "Hỏi Nova về tình hình lớp, kết quả học tập hoặc nhờ soạn nội dung hỗ trợ. Mọi thao tác thay đổi dữ liệu đều cần bạn xác nhận."
                    : tab === "RAG_QUESTION"
                    ? "Hỏi Nova về nội dung môn học — mỗi câu trả lời đều kèm trích dẫn để bạn tự kiểm chứng."
                    : "Chế độ Gia sư: Nova gợi mở từng bước để bạn tự tìm ra đáp án, thay vì đưa lời giải ngay."}
                </p>
              </div>
            )}

            {/* Báo cho người dùng biết đây là lịch sử cũ được khôi phục
                (từ localStorage + API), tránh tưởng nhầm là bug hiển thị
                sai khi mở panel lên đã thấy sẵn tin nhắn. */}
            {hydratedTabs[tab] && current.messages.length > 0 && (
              <p className="pb-1 text-center text-[11px]" style={{ color: "var(--ink-faint)" }}>
                — Tiếp tục cuộc trò chuyện trước —
              </p>
            )}

            {current.messages.map((m, i) => (
              <div key={i} className={`animate-fade flex gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {/* Avatar chỉ ở tin nhắn của Nova - tin nhắn người dùng
                    không cần avatar (họ biết mình là ai), thêm vào chỉ
                    làm chật khung chat vốn đã hẹp. */}
                {m.role === "assistant" && !m.blocked && (
                  <div className="mt-0.5">
                    <NovaAvatar size={22} state={m.status ?? "idle"} />
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

                  {/* Thẻ xác nhận hành động - chỉ hiện 2 nút Xác nhận/Huỷ
                      ở tin nhắn CUỐI CÙNG có pendingAction (tin nhắn cũ
                      trong lịch sử coi như đã xử lý xong về mặt hiển
                      thị dù dữ liệu vẫn còn trong mảng messages). */}
                  {m.pendingAction && (
                    <div
                      className="mt-1.5 rounded-[8px] border px-2.5 py-2"
                      style={{ background: "var(--accent-bg)", borderColor: "var(--border)" }}
                    >
                      <div className="flex items-start gap-1.5">
                        <svg
                          viewBox="0 0 24 24"
                          width="14"
                          height="14"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="mt-0.5 shrink-0"
                          style={{ color: "var(--accent-ink)" }}
                        >
                          <circle cx="12" cy="12" r="10" />
                          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                          <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                        <span className="text-[12px] leading-relaxed" style={{ color: "var(--accent-ink)" }}>
                          {m.pendingAction.arguments_summary}
                        </span>
                      </div>
                      {i === current.messages.length - 1 && (
                        <div className="mt-2 flex gap-1.5">
                          <button
                            // Gửi ngay bằng ĐÚNG luồng gửi tin nhắn hiện
                            // có (handleSend), truyền thẳng text qua
                            // overrideText - KHÔNG qua setInput() vì
                            // handleSend đọc input từ closure của lượt
                            // render lúc bấm, không thấy state vừa đổi.
                            onClick={() => handleSend("Có, làm đi")}
                            disabled={sending}
                            className="rounded-[6px] px-2.5 py-1 text-[11.5px] font-medium text-white disabled:opacity-50"
                            style={{ background: "var(--accent)" }}
                          >
                            Xác nhận
                          </button>
                          <button
                            onClick={() => handleSend("Không, huỷ")}
                            disabled={sending}
                            className="rounded-[6px] border px-2.5 py-1 text-[11.5px] font-medium disabled:opacity-50"
                            style={{ borderColor: "var(--border-strong)", color: "var(--ink-soft)" }}
                          >
                            Huỷ
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Thẻ kết quả hành động - chỉ thông báo, không có nút
                      nào. content chính đã RỖNG với category
                      ACTION_REQUEST (xem comment tại xử lý sự kiện
                      "action_result") nên summary hiển thị đủ ở đây,
                      không bị lặp lại với content. */}
                  {m.actionResult && (
                    <div
                      className="mt-1.5 flex items-start gap-1.5 rounded-[8px] border px-2.5 py-2"
                      style={{
                        background: m.actionResult.success ? "var(--panel-soft)" : "var(--red-bg)",
                        borderColor: m.actionResult.success ? "var(--border)" : "#f0d0d0",
                      }}
                    >
                      {m.actionResult.success ? (
                        <svg
                          viewBox="0 0 24 24"
                          width="14"
                          height="14"
                          fill="none"
                          stroke="var(--teal)"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="mt-0.5 shrink-0"
                        >
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      ) : (
                        <svg
                          viewBox="0 0 24 24"
                          width="14"
                          height="14"
                          fill="none"
                          stroke="var(--red)"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="mt-0.5 shrink-0"
                        >
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      )}
                      <div className="text-[12px] leading-relaxed" style={{ color: "var(--ink)" }}>
                        <span className="font-semibold">{m.actionResult.tool_label_vi}</span>
                        <span> — {m.actionResult.summary}</span>
                      </div>
                    </div>
                  )}

                  {m.citations && m.citations.length > 0 && (
                    <div className="relative mt-1.5">
                      {/* KHÔNG đánh số/hiện danh sách citation riêng lẻ
                          ([1][2][3]...) ra ngoài nữa - gộp thành 1 điểm
                          truy cập duy nhất, đỡ rối giao diện. Bấm thẳng
                          mở luôn nếu chỉ có 1 nguồn; mở menu chọn nếu có
                          nhiều hơn 1, vẫn giữ được khả năng xem TỪNG
                          đoạn tài liệu gốc (không mất tính minh bạch). */}
                      <button
                        onClick={() => {
                          if (m.citations!.length === 1) {
                            openChunk(m.citations![0].chunk_id);
                          } else {
                            setOpenCitationMenuFor(openCitationMenuFor === m ? null : m);
                          }
                        }}
                        disabled={m.citations.length === 1 && chunkLoading === m.citations[0].chunk_id}
                        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium hover:underline disabled:opacity-50"
                        style={{ color: "var(--accent-strong)" }}
                      >
                        <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <polyline points="14 2 14 8 20 8" />
                        </svg>
                        {m.citations.length === 1 && chunkLoading === m.citations[0].chunk_id
                          ? "Đang mở…"
                          : `Xem nguồn tham khảo (${m.citations.length})`}
                      </button>

                      {/* Menu chọn nguồn - chỉ khi có từ 2 citation trở lên */}
                      {openCitationMenuFor === m && m.citations.length > 1 && (
                        <div
                          className="absolute bottom-full left-0 z-10 mb-1.5 w-[240px] overflow-hidden rounded-lg border bg-white shadow-lg"
                          style={{ borderColor: "var(--border)" }}
                        >
                          {m.citations.map((c) => (
                            <button
                              key={c.chunk_id}
                              onClick={() => {
                                setOpenCitationMenuFor(null);
                                openChunk(c.chunk_id);
                              }}
                              disabled={chunkLoading === c.chunk_id}
                              className="block w-full px-3 py-2 text-left text-[11.5px] hover:bg-[var(--panel-soft)] disabled:opacity-50"
                              style={{ color: "var(--ink)" }}
                            >
                              {c.page_number ? `Trang ${c.page_number}` : "Đoạn tài liệu"}
                              {chunkLoading === c.chunk_id && " (đang mở…)"}
                            </button>
                          ))}
                        </div>
                      )}
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
                        // Chỉ hiện 1 icon nhỏ thay vì lộ hẳn con số % ra
                        // ngoài - số liệu kỹ thuật này dễ gây hiểu lầm là
                        // "xác suất đúng" nếu nhìn thấy ngay, nên đẩy vào
                        // tooltip (title) cho ai thực sự cần mới hover xem.
                        <span
                          className="ml-auto inline-flex cursor-help items-center"
                          style={{ color: "var(--ink-faint)" }}
                          title={`Độ khớp tài liệu: ${(m.retrievalSimilarity * 100).toFixed(0)}% - Độ tương đồng ngữ nghĩa của đoạn tài liệu khớp nhất: ${m.retrievalSimilarity.toFixed(3)}. Đây KHÔNG phải xác suất câu trả lời đúng.`}
                          aria-label={`Độ khớp tài liệu: ${(m.retrievalSimilarity * 100).toFixed(0)}%`}
                        >
                          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="12" y1="16" x2="12" y2="11" />
                            <line x1="12" y1="8" x2="12.01" y2="8" />
                          </svg>
                        </span>
                      )}
                    </div>
                  )}

                  {/* Gợi ý câu hỏi tiếp theo - chỉ hiện với tin nhắn cuối
                      cùng của assistant đã stream xong, và có suggestions. */}
                  {m.role === "assistant" &&
                    !m.blocked &&
                    i === current.messages.length - 1 &&
                    !m.streaming &&
                    (suggestedQuestions.length > 0 || suggestionsLoading) && (
                      <div className="mt-2 border-t border-[color:var(--border)] pt-2">
                        <div
                          className="mb-1.5 flex items-center gap-1 text-[10px] font-medium"
                          style={{ color: "var(--ink-faint)" }}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                            <line x1="12" y1="17" x2="12.01" y2="17" />
                          </svg>
                          <span>Gợi ý câu hỏi tiếp theo</span>
                        </div>
                        {suggestionsLoading ? (
                          <div className="flex gap-[3px]">
                            <span className="h-[5px] w-[5px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:0ms]" />
                            <span className="h-[5px] w-[5px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:150ms]" />
                            <span className="h-[5px] w-[5px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:300ms]" />
                          </div>
                        ) : (
                          <div className="flex flex-wrap gap-1.5">
                            {suggestedQuestions.map((q, qi) => (
                              <button
                                key={qi}
                                onClick={() => {
                                  setInput(q);
                                  setSuggestedQuestions([]);
                                  // Focus vào input để user có thể sửa trước khi gửi
                                  document.querySelector<HTMLInputElement>('input[placeholder="Hỏi Nova…"]')?.focus();
                                }}
                                className="rounded-full border px-2.5 py-1 text-[10.5px] transition-colors"
                                style={{
                                  borderColor: "var(--border)",
                                  color: "var(--ink-soft)",
                                  background: "var(--panel-soft)",
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.borderColor = "var(--accent-strong)";
                                  e.currentTarget.style.color = "var(--accent-strong)";
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.borderColor = "var(--border)";
                                  e.currentTarget.style.color = "var(--ink-soft)";
                                }}
                              >
                                {q}
                              </button>
                            ))}
                          </div>
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
            <VoiceInput
              onTranscriptionComplete={(text) => void handleSend(text, true)}
              disabled={sending}
            />
            <button
              onClick={() => handleSend()}
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

      {showPreferences && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" style={{ background: "rgba(10, 12, 30, 0.45)" }} onClick={(e) => e.target === e.currentTarget && setShowPreferences(false)}>
          <div className="w-[440px] max-w-[92vw] rounded-xl border bg-white p-5" style={{ borderColor: "var(--border)" }}>
            <div className="mb-4 flex items-start justify-between">
              <div>
                <div className="text-[15px] font-bold">Cá nhân hóa Nova</div>
                <div className="mt-1 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>Tùy chọn chỉ đổi cách diễn đạt, không đổi dữ liệu hay quyền truy cập.</div>
              </div>
              <button onClick={() => setShowPreferences(false)} aria-label="Đóng">✕</button>
            </div>
            {preferencesLoading ? (
              <div className="py-8 text-center text-[12px]" style={{ color: "var(--ink-soft)" }}>Đang tải tùy chọn…</div>
            ) : (
              <div className="grid gap-3">
                {([
                  ["preferred_language", "Ngôn ngữ", [["auto", "Tự động"], ["vi", "Tiếng Việt"], ["en", "English"]]],
                  ["explanation_depth", "Mức giải thích", [["auto", "Tự động"], ["beginner", "Cơ bản"], ["intermediate", "Trung bình"], ["advanced", "Nâng cao"]]],
                  ["response_length", "Độ dài", [["auto", "Tự động"], ["short", "Ngắn"], ["medium", "Vừa"], ["detailed", "Chi tiết"]]],
                  ["example_style", "Kiểu ví dụ", [["auto", "Tự động"], ["code", "Đoạn mã"], ["analogy", "So sánh dễ hiểu"], ["step_by_step", "Từng bước"]]],
                ] as const).map(([field, label, options]) => (
                  <label key={field} className="grid gap-1 text-[12px] font-medium">
                    {label}
                    <select className="rounded-lg border px-3 py-2 text-[12.5px] font-normal" value={preferences[field]} onChange={(e) => setPreferences((current) => ({ ...current, [field]: e.target.value as NovaPreference[typeof field] }))}>
                      {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                    </select>
                  </label>
                ))}
                <div className="rounded-lg border p-3 text-[11.5px]" style={{ borderColor: "var(--border)", background: "var(--panel-soft)" }}>
                  <div className="font-semibold">Bộ nhớ hội thoại cũ: {memories.length}</div>
                  <div className="mt-1" style={{ color: "var(--ink-soft)" }}>Nova chỉ dùng phần hội thoại đã rời cửa sổ chat gần nhất. Bạn có thể xóa toàn bộ bất kỳ lúc nào.</div>
                  {memories.slice(0, 3).map((memory) => (
                    <div key={memory.conversation_id} className="mt-2 truncate" title={memory.summary}>Phiên #{memory.conversation_id}: {memory.summary}</div>
                  ))}
                  <button className="mt-2 text-[11.5px] font-semibold text-red-600 disabled:opacity-50" onClick={() => void clearConversationMemory()} disabled={preferencesSaving || memories.length === 0}>Xóa toàn bộ bộ nhớ hội thoại</button>
                </div>
                <div className="mt-2 flex gap-2">
                  <button className="btn flex-1" onClick={() => void resetPreferences()} disabled={preferencesSaving}>Đặt lại</button>
                  <button className="btn btn-primary flex-1" onClick={() => void savePreferences()} disabled={preferencesSaving}>{preferencesSaving ? "Đang lưu…" : "Lưu tùy chọn"}</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Summary Modal - tóm tắt cuộc trò chuyện */}
      {showSummary && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          style={{ background: "rgba(10, 12, 30, 0.45)" }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowSummary(false);
          }}
        >
          <div
            className="max-h-[85vh] w-[500px] max-w-[92vw] overflow-y-auto rounded-xl border bg-white p-5"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <NovaAvatar size={22} />
                <div>
                  <div className="text-[14px] font-bold">Tóm tắt cuộc trò chuyện</div>
                  <div className="text-[11px]" style={{ color: "var(--ink-soft)" }}>
                    {current.messages.length} tin nhắn
                  </div>
                </div>
              </div>
              <button
                onClick={() => setShowSummary(false)}
                className="text-[16px] leading-none"
                style={{ color: "var(--ink-faint)" }}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>

            {summaryLoading ? (
              <div className="flex flex-col items-center gap-3 py-8">
                <div className="flex gap-[4px]">
                  <span className="h-[6px] w-[6px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:0ms]" />
                  <span className="h-[6px] w-[6px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:150ms]" />
                  <span className="h-[6px] w-[6px] animate-bounce rounded-full bg-[color:var(--ink-faint)] [animation-delay:300ms]" />
                </div>
                <span className="text-[12px]" style={{ color: "var(--ink-soft)" }}>
                  Đang phân tích cuộc trò chuyện...
                </span>
              </div>
            ) : summaryData ? (
              <div className="space-y-4">
                {/* Summary */}
                <div>
                  <div
                    className="mb-1.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide"
                    style={{ color: "var(--ink-faint)" }}
                  >
                    Tổng kết
                  </div>
                  <div
                    className="whitespace-pre-wrap rounded-[9px] border p-3 text-[12.5px] leading-relaxed"
                    style={{ background: "var(--panel-soft)", borderColor: "var(--border)", color: "var(--ink)" }}
                  >
                    {summaryData.summary}
                  </div>
                </div>

                {/* Key Points */}
                {summaryData.key_points.length > 0 && (
                  <div>
                    <div
                      className="mb-1.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide"
                      style={{ color: "var(--ink-faint)" }}
                    >
                      Điểm chính
                    </div>
                    <div className="space-y-1.5">
                      {summaryData.key_points.map((point, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-2 rounded-[7px] border p-2.5 text-[12px]"
                          style={{ background: "var(--panel-soft)", borderColor: "var(--border)", color: "var(--ink)" }}
                        >
                          <span
                            className="mt-0.5 flex h-[16px] w-[16px] shrink-0 items-center justify-center rounded-full text-[9px] font-bold"
                            style={{ background: "var(--accent)", color: "#fff" }}
                          >
                            {i + 1}
                          </span>
                          <span>{point}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Covered Concepts */}
                {summaryData.covered_concepts.length > 0 && (
                  <div>
                    <div
                      className="mb-1.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide"
                      style={{ color: "var(--ink-faint)" }}
                    >
                      Chủ đề đã học
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {summaryData.covered_concepts.map((concept, i) => (
                        <span
                          key={i}
                          className="rounded-full px-2.5 py-1 text-[11px] font-medium"
                          style={{ background: "var(--accent-bg)", color: "var(--accent-ink)" }}
                        >
                          {concept}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={copySummary}
                    className="flex flex-1 items-center justify-center gap-1.5 rounded-[7px] border px-3 py-2 text-[12px] font-medium transition-colors"
                    style={{ borderColor: "var(--border)", color: "var(--ink-soft)" }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = "var(--accent-strong)";
                      e.currentTarget.style.color = "var(--accent-strong)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = "var(--border)";
                      e.currentTarget.style.color = "var(--ink-soft)";
                    }}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                    {copyStatus === "success" ? "Đã sao chép" : copyStatus === "error" ? "Không sao chép được" : "Sao chép"}
                  </button>
                  <button
                    onClick={handleStartNewConversation}
                    className="btn btn-primary flex flex-1 items-center justify-center gap-1.5"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="12" y1="5" x2="12" y2="19" />
                      <line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    Bắt đầu mới
                  </button>
                </div>
              </div>
            ) : (
              <div className="py-4 text-center text-[12px]" style={{ color: "var(--ink-soft)" }}>
                Không thể tải tóm tắt
              </div>
            )}
          </div>
        </div>
      )}

      {/* Khi panel mở, launcher được ẩn để không tạo thêm một nút X thứ hai. */}
      {!isOpen && (
        <button
          type="button"
          onClick={openPanel}
          className="relative flex h-[58px] items-center gap-2.5 rounded-full border bg-white py-1.5 pl-1.5 pr-4 text-left transition hover:-translate-y-0.5"
          style={{
            borderColor: "#c9dcf1",
            boxShadow: "0 10px 28px rgba(30, 73, 125, 0.2)",
          }}
          aria-label="Chat với Nova - trợ lý học thuật"
        >
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#1764bd] ring-1 ring-blue-200">
            <NovaAvatar size={39} />
          </span>
          <span className="flex items-center gap-2">
            <span className="whitespace-nowrap text-[13.5px] font-bold" style={{ color: "var(--accent-ink)" }}>
              Chat với Nova
            </span>
            <span className="h-2 w-2 rounded-full bg-[#16a394]" aria-hidden="true" />
          </span>
          {unreadCount > 0 && (
            <span
              className="absolute -right-1 -top-1 flex h-[20px] min-w-[20px] items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white"
              style={{ background: "var(--red)", border: "2px solid var(--bg)" }}
            >
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>
      )}
    </div>
  );
}
