from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    is_positive: bool


class FeedbackResponse(BaseModel):
    message_id: int
    is_positive: bool
