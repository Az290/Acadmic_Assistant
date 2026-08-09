from pydantic import BaseModel, Field


class RouteClassifyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class RouteClassifyResponse(BaseModel):
    category: str
    reasoning: str
    needs_retrieval: bool
    classified_by: str
