/**
 * Lớp gọi API duy nhất tới backend - MỌI request từ Frontend đều đi
 * qua đây, không gọi fetch() rải rác ở từng component.
 *
 * credentials: "include" là bắt buộc: backend dùng cookie HttpOnly
 * (không phải Bearer token trong header) để giữ đăng nhập - nếu thiếu
 * tuỳ chọn này, trình duyệt sẽ KHÔNG gửi kèm cookie khi gọi sang domain
 * khác (Frontend chạy cổng 3000, Backend cổng 8001 lúc dev - đây LÀ
 * cross-origin dù cùng "localhost"), khiến mọi request tưởng như chưa
 * đăng nhập dù vừa login thành công.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  // FormData (upload file) cần header "Content-Type: multipart/form-data;
  // boundary=..." do TRÌNH DUYỆT tự sinh - nếu ta set cứng
  // "application/json" ở đây, spread ...options.headers KHÔNG ghi đè
  // được (headers rỗng {} không xoá field đã có), khiến backend nhận
  // body multipart nhưng header lại khai application/json và hiểu sai
  // định dạng. Vì vậy CHỈ set Content-Type mặc định khi body không
  // phải FormData.
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });

  if (!response.ok) {
    // Backend trả lỗi dạng {"detail": "..."} theo chuẩn FastAPI - đọc
    // đúng field đó để hiển thị thông báo có ý nghĩa cho người dùng,
    // thay vì chỉ báo "Lỗi không xác định".
    let detail = `Lỗi ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // response không phải JSON hợp lệ - giữ nguyên thông báo mặc định.
    }
    throw new ApiError(response.status, detail);
  }

  // 204 No Content hoặc response rỗng - không có gì để parse.
  const text = await response.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  postForm: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: "POST", body: formData }), // request() tự bỏ qua Content-Type mặc định khi body là FormData
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  // DELETE không có body - dùng cho xoá enrollment, v.v. Backend trả
  // 204 No Content, request() đã xử lý sẵn trường hợp response rỗng.
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/* ---------- Types khớp với Pydantic schema của backend ---------- */

export type UserRole = "STUDENT" | "INSTRUCTOR" | "ADMIN";

export interface UserPublic {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
}

/**
 * Mỗi vai trò có 1 dashboard riêng - dùng chung ở login, register và
 * trang gốc "/" để 3 nơi không bao giờ lệch nhau khi thêm role mới.
 */
export function dashboardPathForRole(role: UserRole): string {
  switch (role) {
    case "INSTRUCTOR":
      return "/instructor";
    case "ADMIN":
      return "/admin";
    default:
      return "/student";
  }
}

/* ---------- Hồ sơ cá nhân ---------- */

export interface ProfileStats {
  total_questions: number;
  questions_this_week: number;
  quizzes_taken: number;
  avg_mastery: number | null;
}

export type MessageCategory = "RAG_QUESTION" | "SOCRATIC_REQUEST" | "CHITCHAT" | "OFF_TOPIC";

export interface ConversationHistoryItem {
  question: string;
  category: MessageCategory;
  created_at: string;
  source_count: number | null;
}

/* ---------- Tiến độ học tập ---------- */

export interface CourseMasteryPublic {
  course_id: number;
  course_code: string;
  avg_mastery: number;
}

export interface WeakConceptPublic {
  concept_id: number;
  concept_name: string;
  course_id: number;
  course_code: string;
  accuracy: number;
  level: "LOW" | "MID";
}

export interface MasteryOverview {
  overall_mastery: number | null;
  by_course: CourseMasteryPublic[];
  weak_concepts: WeakConceptPublic[];
}

/* ---------- Quiz ôn tập ---------- */

export interface QuizQuestionPublic {
  id: number;
  concept_id: number;
  question: string;
  options: string[];
}

export interface AnswerResponse {
  is_correct: boolean;
  correct_index: number;
  explanation: string;
  streak: number;
  mastered: boolean;
}

/* ---------- Quiz theo BỘ (làm hết rồi nộp 1 lần) ---------- */

/** Bộ câu hỏi cho 1 khái niệm - KHÔNG kèm đáp án đúng (lộ ra thì quiz vô nghĩa). */
export interface QuizSetResponse {
  concept_id: number;
  concept_name: string;
  questions: QuizQuestionPublic[];
}

/** Kết quả 1 câu sau khi nộp cả bộ - đủ dữ liệu để hiển thị lại đề + đáp án đã chọn. */
export interface QuizAnswerResult {
  quiz_question_id: number;
  question: string;
  options: string[];
  selected_index: number;
  correct_index: number;
  is_correct: boolean;
  explanation: string;
}

export interface SubmitAnswersResponse {
  score: number;
  total: number;
  results: QuizAnswerResult[];
  streak: number;
  mastered: boolean;
}

export interface CoursePublic {
  id: number;
  code: string;
  name: string;
  owner_id: number;
}

/** 1 sinh viên trong danh sách lớp (roster) - dùng cho UI quản lý lớp của giảng viên. */
export interface StudentRosterItem {
  user_id: number;
  full_name: string;
  email: string;
  enrolled_at: string;
}

export interface DocumentPublic {
  id: number;
  course_id: number | null;
  title: string;
  status: string;
  license_status: string;
  content_hash: string;
  superseded_by_id: number | null;
  image_count: number;
  // Chuỗi JSON theo CuratorReport (3 bước: injection_scan/quality_gate/
  // dedup) - cảnh báo tự động từ Curator Agent, chỉ THAM KHẢO, giảng
  // viên vẫn tự quyết định duyệt hay từ chối. Dùng parseCuratorReport()
  // bên dưới để đọc an toàn (dữ liệu cũ có thể là text tự do, không
  // phải JSON).
  curator_notes: string | null;
  // Lý do giảng viên ghi khi từ chối tài liệu (text tự do, tách khỏi
  // curator_notes vì khác nguồn/khác cấu trúc).
  rejection_reason: string | null;
  uploader_name?: string;
  uploader_role?: string;
}

/**
 * 1 dòng trong danh sách tài liệu ĐÃ DUYỆT của 1 lớp (GET /v1/documents
 * ?course_id=) - dùng ở trang "Tài liệu" để sinh viên/giảng viên xem
 * lại kho tài liệu, không chỉ upload rồi không bao giờ thấy nữa.
 * chunk_count đã được backend lọc theo quyền đọc của NGƯỜI GỌI.
 */
export interface DocumentSummary {
  id: number;
  title: string;
  created_at: string;
  image_count: number;
  chunk_count: number;
  uploaded_by_name: string;
}

export interface DocumentContentChunk {
  chunk_id: number;
  ord: number;
  page_number: number | null;
  content: string;
  content_type: string;
  context_prefix: string | null;
}

/** Toàn bộ nội dung đọc được của 1 tài liệu (GET /v1/documents/{id}/content), theo đúng thứ tự. */
export interface DocumentContent {
  document_id: number;
  title: string;
  total_chunks: number;
  chunks: DocumentContentChunk[];
}

export type CuratorStepStatus = "pass" | "warn";

export interface CuratorStepResult {
  status: CuratorStepStatus;
  detail: string;
}

export interface CuratorReport {
  injection_scan: CuratorStepResult;
  quality_gate: CuratorStepResult;
  dedup: CuratorStepResult;
}

/**
 * Parse curator_notes an toàn - dữ liệu cũ (tài liệu ingest TRƯỚC khi
 * đổi sang schema JSON) vẫn có thể là text tự do nối bằng "\n", không
 * phải JSON hợp lệ. Trả về null nếu không parse được theo đúng cấu
 * trúc CuratorReport, để component gọi tự quyết định fallback hiển thị.
 */
export function parseCuratorReport(raw: string | null): CuratorReport | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === "object" &&
      "injection_scan" in parsed &&
      "quality_gate" in parsed &&
      "dedup" in parsed
    ) {
      return parsed as CuratorReport;
    }
    return null;
  } catch {
    return null;
  }
}

export interface DocumentPreviewChunk {
  chunk_id: number;
  page_number: number | null;
  content: string;
}

/**
 * Xem trước tài liệu trước khi duyệt - TEXT ĐÃ TRÍCH XUẤT, không phải
 * file gốc: giảng viên cần thấy đúng thứ AI đọc được (PDF scan sẽ ra
 * text rỗng/rác, xem bản gốc không phát hiện ra).
 */
export interface DocumentPreview {
  document_id: number;
  title: string;
  total_chunks: number;
  image_count: number;
  chunks: DocumentPreviewChunk[];
}

/** Nguyên văn 1 đoạn tài liệu - hiện khi bấm vào badge trích dẫn. */
export interface ChunkDetail {
  chunk_id: number;
  content: string;
  page_number: number | null;
  document_title: string;
}

export interface CitationPublic {
  chunk_id: number;
  document_id: number;
  page_number: number | null;
}

/**
 * Hành động Nova ĐỀ XUẤT nhưng CHƯA thực thi, đang chờ người dùng xác
 * nhận ở lượt chat tiếp theo (category "ACTION_REQUEST", tool GHI).
 * arguments_summary là câu tiếng Việt NGƯỜI ĐỌC ĐƯỢC sẵn từ backend -
 * không cần frontend tự diễn giải tham số JSON thô.
 */
export interface PendingActionPublic {
  tool_name: string;
  tool_label_vi: string;
  arguments_summary: string;
}

/** Kết quả THẬT SỰ đã thực thi của 1 tool (sau khi xác nhận, hoặc tool đọc chạy ngay). */
export interface ActionResultPublic {
  tool_name: string;
  tool_label_vi: string;
  success: boolean;
  summary: string;
}

export interface ChatResponse {
  conversation_id: number;
  answer: string;
  category: string;
  citations: CitationPublic[];
  blocked: boolean;
  // 2 field MỚI, OPTIONAL - CHỈ có giá trị khi category="ACTION_REQUEST",
  // và CHỈ 1 trong 2 có giá trị cùng lúc (hoặc cả 2 null nếu Nova chỉ
  // trả lời text thường mà không gọi tool nào) - xem ChatResponse ở
  // backend (app/academic_agent/schemas.py).
  pending_action: PendingActionPublic | null;
  action_result: ActionResultPublic | null;
}

/**
 * 1 tin nhắn đã lưu trong lịch sử hội thoại - dùng để "hydrate" lại
 * ChatBubble khi người dùng quay lại (F5, mở lại panel) với
 * conversationId đã lưu ở localStorage. Sắp cũ -> mới theo thời gian.
 */
export interface MessagePublic {
  message_id: number;
  role: "user" | "assistant";
  content: string;
  citations: CitationPublic[];
  retrieval_similarity: number | null;
  // pending_action phản ánh cột Message.pending_action - CHỈ có ý nghĩa
  // nếu đây là tin nhắn assistant CUỐI CÙNG của conversation (backend
  // không set lại cho tin nhắn cũ). Không có field action_result ở đây
  // (backend không lưu action_result lịch sử, chỉ pending_action).
  pending_action: PendingActionPublic | null;
  created_at: string;
}

/* ---------- Streaming chat (SSE) - dùng cho ChatBubble ---------- */

export interface ConceptPublic {
  id: number;
  course_id: number;
  name: string;
  complexity: number;
}

// Body gửi lên POST /v1/concepts - prerequisites để mảng rỗng ở bản
// đầu (chưa làm UI chọn khái niệm tiên quyết).
export interface CreateConceptRequest {
  course_id: number;
  name: string;
  complexity: number;
  prerequisites?: number[];
}

export type ChatStreamEvent =
  // concept_id: khái niệm hệ thống nhận diện được từ câu hỏi (chế độ
  // Gia sư) - null nếu không khớp khái niệm nào. Hiển thị cho sinh
  // viên biết để họ sửa lại nếu đoán sai.
  | { type: "start"; conversation_id: number; category: string; concept_id: number | null }
  // Tiến trình xử lý - gửi TRƯỚC khi có chữ đầu tiên, để người dùng
  // biết hệ thống đang làm gì thay vì nhìn bong bóng rỗng ~2 giây.
  // sources_found: số đoạn tài liệu tìm được (chỉ có ở stage
  // "generating").
  | { type: "status"; stage: "checking" | "searching" | "generating"; sources_found?: number }
  | { type: "chunk"; text: string }
  // message_id: id câu trả lời vừa lưu - cần để gửi đánh giá 👍/👎.
  // retrieval_similarity: độ khớp tài liệu (0-1), null nếu câu hỏi
  // không cần tra cứu tài liệu (chitchat/off-topic).
  | {
      type: "done";
      citations: CitationPublic[];
      message_id: number;
      retrieval_similarity: number | null;
    }
  | { type: "blocked"; conversation_id: number; reason: string }
  // Nova ĐỀ XUẤT 1 hành động GHI (vd tạo khái niệm), đang chờ người
  // dùng xác nhận ở lượt chat tiếp theo - KHÔNG có "chunk" nào đi kèm
  // sự kiện này trong cùng 1 lượt xử lý (đã đọc kỹ backend
  // app/academic_agent/agent.py::handle_chat_stream, nhánh
  // ACTION_REQUEST: pending_action/action_result và "chunk" LOẠI TRỪ
  // NHAU - "chunk" chỉ được gửi khi KHÔNG có tool nào được gọi).
  | { type: "action_pending"; tool_name: string; tool_label_vi: string; arguments_summary: string }
  // Kết quả THẬT SỰ đã thực thi của 1 tool (tool đọc chạy ngay, hoặc
  // tool ghi sau khi người dùng xác nhận/huỷ) - cũng KHÔNG kèm "chunk".
  | { type: "action_result"; tool_name: string; tool_label_vi: string; success: boolean; summary: string };

/**
 * Gửi 1 câu hỏi tới /v1/chat/stream và gọi onEvent() cho từng sự kiện
 * SSE nhận được, NGAY KHI nó tới (không đợi cả response xong).
 *
 * Dùng fetch + ReadableStream thay vì EventSource chuẩn của trình
 * duyệt vì EventSource CHỈ hỗ trợ GET, không gửi được body JSON hay
 * cookie theo cách ta cần kiểm soát - fetch cho toàn quyền tự parse
 * khung "data: ...\n\n" giống hệt chuẩn SSE.
 */
export async function streamChat(
  body: {
    message: string;
    conversation_id?: number;
    course_id?: number;
    force_category?: "RAG_QUESTION" | "SOCRATIC_REQUEST";
    concept_id?: number;
  },
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/v1/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    let detail = `Lỗi ${response.status}`;
    try {
      const parsed = await response.json();
      if (parsed?.detail) detail = parsed.detail;
    } catch {
      // không phải JSON - giữ thông báo mặc định
    }
    throw new ApiError(response.status, detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Mỗi sự kiện SSE kết thúc bằng 1 dòng trống ("\n\n") - tách theo
    // đó, phần còn dư (chưa đủ 1 sự kiện trọn vẹn) giữ lại trong buffer
    // chờ đợt đọc tiếp theo (network có thể cắt vụn 1 sự kiện thành
    // nhiều lần đọc).
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      onEvent(JSON.parse(line.slice(6)) as ChatStreamEvent);
    }
  }
}

/* ---------- Dashboard giảng viên (analytics tổng hợp theo lớp) ---------- */

export interface CategoryCount {
  category: string;
  count: number;
}

export interface InsufficientContextRate {
  total_rag_questions: number;
  insufficient_count: number;
  rate: number; // 0.0 - 1.0
}

export interface SecurityAlertSummary {
  blocked_by: string;
  count: number;
}

export interface ConceptGap {
  concept_id: number | null;
  concept_name: string;
  total_questions: number;
  unanswered_questions: number;
  gap_rate: number; // 0.0 - 1.0
}

export interface StudentNeedingSupport {
  user_id: number;
  full_name: string;
  mastery: number;
  weakest_concept_name: string | null;
  question_count: number;
}

export interface MasteryDistributionBucket {
  label: string;
  student_count: number;
}

export interface ClassAnalytics {
  course_id: number;
  total_students: number;
  students_with_data: number;
  // Sinh viên chưa làm quiz nào - KHÔNG tính vào phân bố/nhóm cần hỗ trợ
  students_without_data: number;
  avg_mastery: number | null;
  needing_support_count: number;
  distribution: MasteryDistributionBucket[];
  students_needing_support: StudentNeedingSupport[];
}

export interface PopularConcept {
  concept_id: number;
  concept_name: string;
  question_count: number;
  avg_retrieval_similarity: number | null;
  feedback_count: number;
  // null = CHƯA ĐỦ dữ liệu đánh giá (khác 0 = đã có phiếu, toàn tiêu cực)
  positive_rate: number | null;
  needs_attention: boolean;
}

export interface InstructorAnalytics {
  course_id: number;
  total_messages: number;
  category_breakdown: CategoryCount[];
  insufficient_context: InsufficientContextRate;
  security_alerts: SecurityAlertSummary[];
  concept_gaps: ConceptGap[];
}

/* ---------- Proactive AI Toast (gợi ý khái niệm yếu nhất) ---------- */

export interface WeakestConceptPublic {
  concept_id: number;
  concept_name: string;
  course_id: number;
  n_obs: number;
  n_correct: number;
  accuracy: number;
}

/**
 * Phát sự kiện cho ChatBubble (component/ChatBubble.tsx) mở panel ở
 * tab Gia sư với đúng lớp + khái niệm đã điền sẵn - xem comment trong
 * ChatBubble.tsx lý do dùng CustomEvent thay vì Context.
 */
export function openTutorChat(courseId: number, conceptId: number) {
  window.dispatchEvent(new CustomEvent("open-tutor-chat", { detail: { courseId, conceptId } }));
}

/* ---------- Eval Dashboard (chỉ ADMIN) ---------- */

export interface EvalRunSummary {
  id: number;
  git_commit_hash: string | null;
  model_version: string;
  dataset_version: string;
  total_cases: number;
  errors: number;
  category_accuracy: number;
  avg_recall_at_k: number | null;
  avg_judge_score: number | null;
  judge_cases_scored: number;
  created_at: string;
}

export interface EvalCaseResultPublic {
  id: number;
  case_id: string;
  expected_category: string;
  actual_category: string | null;
  category_match: boolean | null;
  recall_at_k: number | null;
  judge_score: number | null;
  judge_reasoning: string | null;
  answer_preview: string | null;
  latency_s: number | null;
  error: string | null;
}

export interface EvalRunDetail extends EvalRunSummary {
  cases: EvalCaseResultPublic[];
}

/* ---------- Bài tập (giao bài + chấm tự động) ---------- */

export interface AssignmentPublic {
  id: number;
  course_id: number;
  title: string;
  description: string | null;
  due_at: string | null;
  question_count: number;
  my_score: number | null;
  my_total: number | null;
  submitted: boolean;
}

export interface AssignmentQuestionPublic {
  quiz_question_id: number;
  ord: number;
  question: string;
  options: string[];
}

export interface AssignmentDetail {
  id: number;
  title: string;
  description: string | null;
  due_at: string | null;
  questions: AssignmentQuestionPublic[];
}

export interface AnswerResult {
  quiz_question_id: number;
  is_correct: boolean;
  correct_index: number;
  explanation: string;
}

export interface SubmitAssignmentResponse {
  score: number;
  total: number;
  results: AnswerResult[];
}

export interface StudentResultSummary {
  user_id: number;
  full_name: string;
  score: number;
  total: number;
  submitted_at: string;
}

export interface ConceptDifficulty {
  concept_id: number;
  concept_name: string;
  correct_count: number;
  total_count: number;
  accuracy: number;
}

export interface AssignmentResults {
  assignment_id: number;
  title: string;
  submitted_count: number;
  enrolled_count: number;
  average_score: number;
  total_questions: number;
  students: StudentResultSummary[];
  concept_difficulty: ConceptDifficulty[];
}

/* ---------- Sinh + duyệt câu hỏi trước khi giao bài (luồng mới) ---------- */

// Câu hỏi NHÁP giảng viên vừa sinh - kèm correct_index vì đây là màn hình
// DUYỆT của giảng viên (khác AssignmentQuestionPublic dành cho sinh viên).
export interface GeneratedQuizQuestion {
  id: number;
  concept_id: number;
  concept_name: string;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

export interface GenerateQuestionsRequest {
  course_id: number;
  concept_ids: number[];
  num_questions_per_concept: number;
}

/** Giảng viên TỰ SOẠN 1 câu hỏi (không qua AI) để thêm vào đề đang duyệt. */
export interface CreateQuizQuestionRequest {
  concept_id: number;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

/** Góp ý để AI sinh lại 1 câu hỏi, vd "đáp án đúng đang sai", "câu này trùng câu 2". */
export interface RegenerateQuizQuestionRequest {
  feedback: string;
}

export interface UpdateQuizQuestionRequest {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

/* ---------- Cost Dashboard + Pipeline Visualization ---------- */

export interface CostSummary {
  total_messages_measured: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  avg_cost_per_message_usd: number;
  projected_monthly_usd_per_100_students: number;
}

export interface PipelineStepTiming {
  step: string;
  avg_ms: number;
  p95_ms: number;
}

export interface PipelineTiming {
  total_messages_measured: number;
  steps: PipelineStepTiming[];
  avg_total_ms: number;
}

/* ---------- Suggested Questions ---------- */

/**
 * Lay danh sach cau hoi goi y dua tren context cua cuoc tro chuyen.
 * Backend se phan tich conversation hien tai de dua ra 3-5 cau hoi
 * lien quan ma nguoi dung co the nam nhuong hoac tim hieu them.
 */
export async function getSuggestedQuestions(
  conversationId: number
): Promise<string[]> {
  try {
    return await api.get<string[]>(`/v1/chat/${conversationId}/suggested-questions`);
  } catch {
    // Neu API chua co, tra ve mock data de co the test UI
    return getMockSuggestedQuestions();
  }
}

/** Mock data khi backend chua implement endpoint */
function getMockSuggestedQuestions(): string[] {
  return [
    "Ban co the giai thich ro hon khong?",
    "Cho vi du cu the duoc khong?",
    "Co cach nao khac de giai quyet khong?",
  ];
}

/* ---------- Conversation Summary ---------- */

/** Du lieu tom tat cuoc tro chuyen */
export interface ConversationSummary {
  summary: string;
  key_points: string[];
  covered_concepts: string[];
  timestamp: string;
}

/**
 * Lay tom tat cuoc tro chuyen - phan tich toan bo lich su de tao
 * summary, key points va covered concepts.
 */
export async function getConversationSummary(
  conversationId: number
): Promise<ConversationSummary> {
  return await api.get<ConversationSummary>(`/v1/chat/${conversationId}/summary`);
}

/* ---------- Learning Path ---------- */

export interface ConceptProgressPublic {
  id: number;
  name: string;
  complexity: number;
  mastery: number | null;
  status: "completed" | "in_progress" | "available" | "locked" | "not_started";
  prerequisites: number[];
  estimated_time_minutes: number;
}

export interface RecommendationPublic {
  // "start_here": sinh viên chưa làm quiz nào - backend gợi ý concept
  // dễ nhất để bắt đầu (xem app/learning/learning_path.py).
  type: "next_learn" | "continue" | "review" | "start_here";
  concept_id: number;
  concept_name: string;
  reason: string;
  priority: number;
}

export interface LearningPathResponse {
  course_id: number;
  course_name: string;
  concepts: ConceptProgressPublic[];
  recommendations: RecommendationPublic[];
}

/**
 * Lấy learning path cho 1 course cụ thể.
 */
export async function getLearningPath(courseId: number): Promise<LearningPathResponse> {
  return await api.get<LearningPathResponse>(`/v1/learning-path?course_id=${courseId}`);
}
