from pydantic import BaseModel


class DocumentPublic(BaseModel):
    id: int
    course_id: int
    title: str
    status: str
    license_status: str
    content_hash: str

    model_config = {"from_attributes": True}
