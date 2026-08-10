from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
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


class ChatResponse(BaseModel):
    conversation_id: int
    answer: str
    category: str
    citations: list[CitationPublic] = []
    blocked: bool = False
