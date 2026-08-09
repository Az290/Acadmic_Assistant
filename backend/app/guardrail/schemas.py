from pydantic import BaseModel, Field


class GuardrailCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    direction: str = Field(default="input", pattern="^(input|output)$")


class GuardrailCheckResponse(BaseModel):
    allowed: bool
    reason: str | None = None
    blocked_by: str | None = None
