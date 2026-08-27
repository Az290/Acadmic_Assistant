from pydantic import BaseModel


class DocumentPublic(BaseModel):
    id: int
    course_id: int | None
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


class ApproveDocumentRequest(BaseModel):
    course_ids: list[int]


class DocumentSummary(BaseModel):
    """
    1 dòng trong danh sách tài liệu ĐÃ DUYỆT của 1 lớp - dùng cho trang
    "Tài liệu" của sinh viên/giảng viên (GET /v1/documents?course_id=).

    KHÁC DocumentPublic: không lộ curator_notes/rejection_reason (thông
    tin nội bộ quy trình duyệt, sinh viên không cần thấy), thay vào đó
    thêm chunk_count (đã lọc quyền đọc của NGƯỜI GỌI, không phải tổng số
    chunk thô của tài liệu) và uploaded_by_name để biết ai đóng góp.
    """

    id: int
    title: str
    created_at: str
    image_count: int
    chunk_count: int
    uploaded_by_name: str


class DocumentContentChunk(BaseModel):
    chunk_id: int
    ord: int
    page_number: int | None
    content: str
    content_type: str
    context_prefix: str | None


class DocumentContent(BaseModel):
    """
    Toàn bộ nội dung ĐỌC ĐƯỢC của 1 tài liệu, theo đúng thứ tự (ord) -
    dùng khi sinh viên bấm "Đọc nội dung" trên trang Tài liệu.
    """

    document_id: int
    title: str
    total_chunks: int
    chunks: list[DocumentContentChunk]
