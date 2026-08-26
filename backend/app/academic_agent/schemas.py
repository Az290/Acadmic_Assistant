from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def _reject_blank_message(cls, value: str) -> str:
        """
        Chặn câu hỏi CHỈ gồm khoảng trắng - PHÁT HIỆN QUA TEST HỒI QUY:
        min_length=1 của Pydantic đếm KÝ TỰ THÔ, nên chuỗi "     " (5 dấu
        cách) lọt qua và chạy trọn pipeline: Guardrail + Router + sinh câu
        trả lời, tốn 1 lượt gọi OpenAI THẬT cho một câu rỗng nghĩa, đồng
        thời tạo ra 1 Conversation rác trong database.

        Trước khi sửa, hành vi KHÔNG NHẤT QUÁN: "" trả 422 còn "   " trả
        200 - cùng là "người dùng không nhập gì" nhưng 2 kết quả khác hẳn.

        Trả về chuỗi ĐÃ strip: các bước sau (embedding, so khớp khái niệm)
        không phải xử lý khoảng trắng thừa ở đầu/cuối nữa.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("Câu hỏi không được để trống.")
        return stripped
    conversation_id: int | None = None
    course_id: int | None = None
    # ChatBubble có 2 tab tường minh ("Hỏi đáp"/"Gia sư") - khi người
    # dùng chọn 1 tab, frontend gửi kèm giá trị này để ÉP category thay
    # vì để Router Agent tự đoán qua nội dung câu hỏi. Chỉ chấp nhận
    # 2 giá trị cần retrieval (RAG_QUESTION/SOCRATIC_REQUEST) - CHITCHAT/
    # OFF_TOPIC không có tab riêng, luôn để Router tự phát hiện.
    force_category: str | None = Field(default=None, pattern="^(RAG_QUESTION|SOCRATIC_REQUEST)$")
    # Chế độ gia sư: sinh viên chỉ định tường minh mình đang hỏi về
    # khái niệm nào (dùng khi hệ thống tự đoán sai). Bỏ trống -> hệ
    # thống tự xác định bằng so khớp ngữ nghĩa.
    concept_id: int | None = None


class CitationPublic(BaseModel):
    chunk_id: int
    document_id: int
    page_number: int | None


class PendingActionPublic(BaseModel):
    """
    Hành động Nova ĐỀ XUẤT nhưng CHƯA thực thi, đang chờ người dùng xác
    nhận ở lượt chat tiếp theo (category ACTION_REQUEST, tool GHI - xem
    app/academic_agent/tools.py::TOOLS_REQUIRING_CONFIRMATION).

    arguments_summary: text tiếng Việt NGƯỜI ĐỌC ĐƯỢC (vd "Tạo khái niệm
    'Đệ quy', độ khó 3, cho lớp CS101") - CỐ Ý KHÔNG PHẢI JSON thô, để
    hiển thị thẳng lên giao diện xác nhận mà không cần frontend tự diễn
    giải cấu trúc tham số.
    """

    tool_name: str
    tool_label_vi: str
    arguments_summary: str


class ActionResultPublic(BaseModel):
    """Kết quả THẬT SỰ đã thực thi của 1 tool (sau khi người dùng xác nhận, hoặc tool đọc chạy ngay)."""

    tool_name: str
    tool_label_vi: str
    success: bool
    summary: str


class ChatResponse(BaseModel):
    conversation_id: int
    answer: str
    category: str
    citations: list[CitationPublic] = []
    blocked: bool = False
    # 2 field MỚI, OPTIONAL (mặc định None) - CHỈ có giá trị khi
    # category="ACTION_REQUEST" (xem app/academic_agent/agent.py). Cùng
    # lúc CHỈ 1 trong 2 field có giá trị: pending_action khi Nova vừa ĐỀ
    # XUẤT 1 hành động GHI cần xác nhận, action_result khi 1 tool vừa
    # THỰC SỰ được thực thi (tool đọc chạy ngay, hoặc tool ghi sau khi
    # người dùng xác nhận/huỷ).
    pending_action: PendingActionPublic | None = None
    action_result: ActionResultPublic | None = None


class MessagePublic(BaseModel):
    """
    1 tin nhắn trong lịch sử hội thoại - dùng cho GET
    /v1/chat/{conversation_id}/messages để frontend "hydrate" lại
    ChatBubble sau khi F5/đăng nhập lại.

    Field đặt tên khớp đúng những gì ChatBubble.tsx cần render lại 1
    tin nhắn đã lưu: role/content/citations như ChatResponse ở trên,
    cộng thêm message_id (để feedback/actions gắn đúng tin nhắn) và
    retrieval_similarity (hiển thị "Độ khớp tài liệu", NULL với
    role='user' hoặc câu hỏi không cần retrieval - xem comment cột
    Message.retrieval_similarity trong db/models.py).

    pending_action: phản ánh cột Message.pending_action nếu tin nhắn
    này (PHẢI là tin nhắn CUỐI CÙNG của conversation) đang có 1 hành
    động chờ xác nhận - để frontend "hydrate" lại đúng trạng thái UI
    xác nhận nếu người dùng F5 giữa lúc đang chờ.
    """

    message_id: int
    role: str
    content: str
    citations: list[CitationPublic] = []
    retrieval_similarity: float | None = None
    pending_action: PendingActionPublic | None = None
    created_at: datetime
