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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
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
    request<T>(path, { method: "POST", body: formData, headers: {} }), // KHÔNG set Content-Type - trình duyệt tự thêm boundary đúng cho multipart
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

export interface CoursePublic {
  id: number;
  code: string;
  name: string;
  owner_id: number;
}

export interface DocumentPublic {
  id: number;
  course_id: number;
  title: string;
  status: string;
  license_status: string;
  content_hash: string;
  superseded_by_id: number | null;
  image_count: number;
  // Cảnh báo tự động từ Curator Agent (nghi ngờ chỉ dẫn ẩn, chất
  // lượng thấp, gần trùng tài liệu khác) - chỉ THAM KHẢO, giảng viên
  // vẫn tự quyết định duyệt hay từ chối.
  curator_notes: string | null;
}

export interface CitationPublic {
  chunk_id: number;
  document_id: number;
  page_number: number | null;
}

export interface ChatResponse {
  conversation_id: number;
  answer: string;
  category: string;
  citations: CitationPublic[];
  blocked: boolean;
}

/* ---------- Streaming chat (SSE) - dùng cho ChatBubble ---------- */

export interface ConceptPublic {
  id: number;
  course_id: number;
  name: string;
  complexity: number;
}

export type ChatStreamEvent =
  // concept_id: khái niệm hệ thống nhận diện được từ câu hỏi (chế độ
  // Gia sư) - null nếu không khớp khái niệm nào. Hiển thị cho sinh
  // viên biết để họ sửa lại nếu đoán sai.
  | { type: "start"; conversation_id: number; category: string; concept_id: number | null }
  | { type: "chunk"; text: string }
  | { type: "done"; citations: CitationPublic[] }
  | { type: "blocked"; conversation_id: number; reason: string };

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

export interface InstructorAnalytics {
  course_id: number;
  total_messages: number;
  category_breakdown: CategoryCount[];
  insufficient_context: InsufficientContextRate;
  security_alerts: SecurityAlertSummary[];
  concept_gaps: ConceptGap[];
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
