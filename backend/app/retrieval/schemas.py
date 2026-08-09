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
