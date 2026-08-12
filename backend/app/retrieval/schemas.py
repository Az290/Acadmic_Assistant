from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)


class SearchResultPublic(BaseModel):
    chunk_id: int
    document_id: int
    content: str
    content_type: str
    page_number: int | None
    context_prefix: str | None
    score: float

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultPublic]


class ChunkDetail(BaseModel):
    """
    Nguyên văn 1 đoạn tài liệu - hiện khi người học bấm vào badge trích
    dẫn để kiểm chứng câu trả lời của AI dựa trên đoạn nào.
    """

    chunk_id: int
    content: str
    page_number: int | None
    document_title: str
