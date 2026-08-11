from pydantic import BaseModel


class DocumentPublic(BaseModel):
    id: int
    course_id: int
    title: str
    status: str
    license_status: str
    content_hash: str
    superseded_by_id: int | None = None
    image_count: int = 0
    # Chuỗi JSON theo app.curator.schemas.CuratorReport - frontend tự
    # JSON.parse() để render dạng pipeline 3 bước.
    curator_notes: str | None = None
    rejection_reason: str | None = None

    model_config = {"from_attributes": True}


class PendingDocumentPublic(DocumentPublic):
    """
    Tài liệu trong hàng chờ duyệt - BỔ SUNG thông tin người đóng góp.

    Cần thiết từ khi sinh viên cũng được đóng góp tài liệu: giảng viên
    phải biết file này do đồng nghiệp hay do sinh viên gửi lên để cân
    nhắc mức độ tin cậy khi duyệt.
    """

    uploader_name: str
    uploader_role: str


class RejectDocumentRequest(BaseModel):
    reason: str | None = None
