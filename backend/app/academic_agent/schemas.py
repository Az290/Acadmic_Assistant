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


class ChatResponse(BaseModel):
    conversation_id: int
    answer: str
    category: str
    citations: list[CitationPublic] = []
    blocked: bool = False
