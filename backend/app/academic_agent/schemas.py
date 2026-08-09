from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    course_id: int | None = None


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
