"""
Định nghĩa cấu trúc Database bằng SQLAlchemy (ORM).

"ORM" (Object-Relational Mapping) nghĩa là: thay vì viết SQL thô như
    CREATE TABLE document (id BIGSERIAL PRIMARY KEY, ...)
ta viết một class Python, và thư viện tự dịch nó thành SQL.

Lợi ích thực dụng cho dự án này:
1. An toàn mặc định: mọi câu truy vấn qua SQLAlchemy đều tự động dùng
   "parameterized query" -> chống SQL injection ngay từ đầu, không cần
   nhớ tự làm thủ công mỗi lần viết query mới.
2. Dễ đọc, dễ sửa: thêm 1 cột chỉ là thêm 1 dòng Python, không phải nhớ
   cú pháp ALTER TABLE.
3. Kết hợp với Alembic (công cụ đi kèm) để quản lý "lịch sử thay đổi"
   database - giống Git nhưng cho cấu trúc bảng.

Các bảng ở đây là bộ tối thiểu cần cho: lưu tài liệu, tìm kiếm ngữ nghĩa
(RAG), đăng nhập/phân quyền, và lưu lịch sử chat. Các bảng nâng cao hơn
(HITL, audit log, BKT...) sẽ thêm khi hệ thống thực sự cần tới chúng.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

# Kích thước vector embedding: cố định 1536 vì ta dùng model
# OpenAI "text-embedding-3-small".
# Nếu sau này đổi sang model embedding khác có số chiều khác,
# sẽ cần một bảng/cột mới - không sửa trực tiếp cột này để tránh
# làm hỏng dữ liệu embedding cũ.
EMBEDDING_DIM = 1536


class Base(DeclarativeBase):
    """Lớp gốc mà mọi bảng kế thừa - quy ước bắt buộc của SQLAlchemy."""

    pass


class Course(Base):
    """
    Một môn học / "kênh lớp" (vd: CS301 - Machine Learning, hoặc lớp
    riêng của một giáo viên trên hệ thống khoá học ngoài).

    Vì sao cần bảng riêng thay vì chỉ lưu "course_code" dạng chữ tự do
    trong bảng document/chunk: để có một nơi duy nhất quản lý danh sách
    môn học hợp lệ, và sau này mở rộng thêm thông tin (giảng viên phụ
    trách, học kỳ...) mà không phải sửa các bảng khác.

    owner_id: giáo viên đã TẠO lớp này. Dùng để kiểm tra
    quyền - chỉ chính giáo viên sở hữu lớp mới được thêm học sinh vào
    lớp đó, không phải bất kỳ INSTRUCTOR nào trong hệ thống.
    """

    __tablename__ = "course"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppUser(Base):
    """
    Người dùng hệ thống: sinh viên, giảng viên, hoặc admin.

    Đặt tên "app_user" thay vì "user" vì USER là từ khóa dành riêng
    trong Postgres (dùng để chỉ người đang kết nối DB) - đặt trùng tên
    dễ gây lỗi khó hiểu.

    password_hash: KHÔNG BAO GIỜ lưu mật khẩu gốc. Cột này lưu một
    chuỗi "băm" một chiều (không giải mã ngược lại được mật khẩu gốc).
    Việc băm mật khẩu thực hiện ở tầng code (app/auth/security.py),
    bảng này chỉ định nghĩa chỗ lưu.

    role: nền tảng của toàn bộ phân quyền (RBAC). Khi đăng nhập, giá
    trị này được "đóng gói" vào JWT để mọi API sau đó biết đang phục
    vụ ai mà không cần tra lại DB mỗi lần.
    """

    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint("role IN ('STUDENT','INSTRUCTOR','ADMIN')", name="ck_app_user_role"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """
    Vé "xin cấp lại" access token mới, không cần đăng nhập lại bằng
    mật khẩu.

    Khác với access token (JWT - tự chứa thông tin, backend KHÔNG cần
    tra DB để xác minh), refresh token là một bản ghi THẬT trong
    database - đây chính là điểm mấu chốt cho phép "thu hồi": muốn vô
    hiệu hoá 1 phiên đăng nhập, chỉ cần đánh dấu dòng tương ứng ở đây,
    có hiệu lực ngay lập tức (khác access token JWT, phải đợi hết hạn
    tự nhiên vì backend không tra DB để kiểm tra JWT còn "sống" hay không).

    token_hash: KHÔNG lưu refresh token gốc (dạng chuỗi ngẫu nhiên) vào
    DB - cùng triết lý với password_hash: nếu database bị lộ, kẻ tấn
    công không lấy được token dùng được ngay, phải "đảo ngược" hash
    (không khả thi với SHA-256).

    is_used + used_at: cùng nhau hiện thực hoá "rotation với grace
    period" - mỗi refresh token chỉ nên dùng 1 lần để xin access token
    mới, nhưng trong thực tế nhiều request có thể vô tình cùng gọi
    refresh song song (vd: nhiều tab/nhiều thành phần trang cùng phát
    hiện access token hết hạn gần như đồng thời). Nếu chặn cứng "dùng
    lần 2 là coi như bị đánh cắp", các request hợp lệ đến sau sẽ bị
    hiểu nhầm và tự đăng xuất người dùng thật một cách sai.

    Giải pháp: khi 1 token bị dùng lần đầu, ghi used_at (thời điểm).
    Token gốc mới đã phát ra thay thế được ghi nhớ tạm thời trong bộ
    nhớ của process (KHÔNG lưu vào cột nào ở đây - xem app/auth/refresh.py)
    để có thể trả lại đúng cho request đến sau trong grace period, mà
    không phải lưu 1 bí mật dạng đọc được vào database. Chỉ khi dùng
    lại sau khoảng grace period mới coi là dấu hiệu bị đánh cắp thật
    và thu hồi toàn bộ phiên.
    """

    __tablename__ = "refresh_token"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Enrollment(Base):
    """
    "Ai thuộc lớp nào" - đây chính là bảng hiện thực hoá ý tưởng
    "kênh riêng của giáo viên": 1 dòng = 1 user (học sinh hoặc giáo
    viên trợ giảng) đã được thêm vào 1 course.

    Khoá chính là CẶP (user_id, course_id) - không có cột "id" riêng,
    vì bản chất bảng này chỉ diễn tả một QUAN HỆ (user X có thuộc lớp Y
    không), không phải một thực thể độc lập cần định danh riêng. Cách
    này cũng tự động chặn việc thêm trùng 1 học sinh vào cùng 1 lớp 2 lần.

    role_in_course: tách biệt với `role` toàn cục ở app_user. Ví dụ một
    người có role toàn cục là INSTRUCTOR vẫn có thể là STUDENT ở một
    lớp khác (đi học lại 1 khoá của đồng nghiệp) - dù trường hợp này
    hiếm, thiết kế tách riêng giúp không bị bó buộc sau này.

    Bảng này quyết định TRỰC TIẾP kết quả tìm kiếm tài liệu: khi học
    sinh hỏi AI, câu SQL sẽ join qua bảng này để biết "user đang hỏi
    thuộc những course_id nào", rồi chỉ tìm chunk trong các course đó.
    """

    __tablename__ = "enrollment"
    __table_args__ = (
        CheckConstraint(
            "role_in_course IN ('STUDENT','INSTRUCTOR')", name="ck_enrollment_role"
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), primary_key=True
    )
    course_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course.id"), primary_key=True
    )
    role_in_course: Mapped[str] = mapped_column(String(20), nullable=False, default="STUDENT")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    """
    Một tài liệu gốc đã upload (1 file PDF/PPTX/... = 1 dòng ở đây).

    Đây là bảng "gốc" - mọi chunk (đoạn văn bản cắt nhỏ) đều thuộc về
    một document. Khi cần biết "đoạn văn này trích từ file nào, trang
    mấy", ta lần theo document_id trong bảng chunk để nối về đây.

    license_status: cờ bắt buộc về bản quyền. Tài liệu RESTRICTED
    (vd: giáo trình thương mại không có phép) sẽ bị loại khỏi kết quả
    tìm kiếm bằng điều kiện SQL, không dựa vào AI "tự biết đừng dùng".
    """

    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(
            "license_status IN ('OWNED','LICENSED','OPEN','RESTRICTED')",
            name="ck_document_license_status",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PROCESSING','PENDING_REVIEW','APPROVED','REJECTED','ARCHIVED')",
            name="ck_document_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    course_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("course.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)  # đường dẫn tới file gốc
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # chống trùng lặp
    license_status: Mapped[str] = mapped_column(String(20), nullable=False, default="RESTRICTED")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    uploaded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Tự trỏ tới document MỚI HƠN đã thay thế document này (cùng course,
    # cùng title, upload sau). NULL nghĩa là đây vẫn là bản mới nhất.
    #
    # Vì sao không XOÁ bản cũ khi có bản mới: (1) chunk cũ có thể đang
    # được trích dẫn trong lịch sử chat cũ (message.citations) - xoá
    # sẽ làm trích dẫn cũ trỏ vào hư không; (2) giữ lại cho phép truy
    # vết/khôi phục nếu bản mới upload nhầm. Việc dọn dữ liệu cũ (xoá
    # hẳn chunk + vector không dùng nữa) để dành cho một job nền định
    # kỳ sau này, tách khỏi luồng upload cho nhanh.
    superseded_by_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("document.id"), nullable=True
    )

    # Số lượng ảnh/hình vẽ đã GẶP nhưng KHÔNG xử lý được nội dung (chưa
    # có OCR/vision) - dùng để biết tài liệu có bao nhiêu phần "trống"
    # về mặt thông tin, làm cơ sở quyết định có cần đầu tư OCR sau này
    # không, thay vì làm mù quáng ngay từ đầu.
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Vector "đại diện" cho toàn bộ tài liệu - trung bình cộng vector
    # của mọi chunk (tính miễn phí, tái dùng vector đã embed lúc ingest,
    # KHÔNG tốn thêm lượt gọi API nào). Dùng để phát hiện tài liệu GẦN
    # TRÙNG (near-duplicate) với tài liệu khác trong cùng lớp - khác
    # content_hash (chỉ bắt trùng TUYỆT ĐỐI từng byte).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    # Ghi chú của Curator Agent (Tác vụ #13) - cảnh báo tự động phát
    # hiện lúc ingest (nghi ngờ prompt injection ẩn trong file, chất
    # lượng thấp, gần trùng tài liệu khác...), hiển thị cho giảng viên
    # THAM KHẢO lúc duyệt. CHỦ Ý không tự động từ chối tài liệu chỉ vì
    # có cảnh báo - con người vẫn là người quyết định cuối cùng (đúng
    # tinh thần HITL, và tránh chặn nhầm vì rule-based có thể báo sai
    # với nội dung học thuật hợp lệ, vd sách có đoạn code mẫu chứa cụm
    # từ trùng pattern injection).
    #
    # LƯU DẠNG CHUỖI JSON theo app.curator.schemas.CuratorReport (3 bước
    # cố định: injection_scan/quality_gate/dedup) - KHÔNG còn là text tự
    # do. Cột khác (rejection_reason) lưu riêng lý do từ chối của giảng
    # viên, tránh trộn 2 nguồn dữ liệu khác cấu trúc vào cùng 1 cột.
    curator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lý do giảng viên từ chối tài liệu (điền lúc gọi POST .../reject) -
    # tách khỏi curator_notes vì đó là JSON có schema cố định do máy tạo,
    # còn đây là text tự do do con người viết.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    """
    Một đoạn văn bản đã cắt nhỏ từ document, kèm vector embedding của nó.

    Đây là bảng QUAN TRỌNG NHẤT về mặt kỹ thuật - toàn bộ tính năng
    "tìm kiếm ngữ nghĩa" (semantic search / RAG) hoạt động dựa trên
    cột `embedding` ở đây.

    Hai điểm mấu chốt về an toàn nằm ngay ở tầng dữ liệu (không phải
    ở lời dặn AI trong prompt):

    - is_solution: nếu True, chunk này chứa đáp án bài tập tính điểm.
      Khi truy vấn tìm kiếm cho sinh viên, ta thêm điều kiện
      "WHERE is_solution = FALSE" -> AI không bao giờ "nhìn thấy"
      đáp án, nên không thể lỡ đưa ra dù prompt có bị bẻ khoá.

    - visibility + course_id: quyết định ai được thấy chunk này.
      Câu truy vấn sẽ luôn có điều kiện lọc theo môn học sinh viên
      đã đăng ký, thực hiện ngay trong SQL WHERE (không lọc sau khi
      đã có kết quả) - đây là nguyên tắc "ACL pre-filter".
    """

    __tablename__ = "chunk"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('PUBLIC','COURSE','INSTRUCTOR_ONLY')", name="ck_chunk_visibility"
        ),
        CheckConstraint(
            "content_type IN ('TEXT','TABLE')", name="ck_chunk_content_type"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("document.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("course.id"), nullable=False)
    ord: Mapped[int] = mapped_column(Integer, nullable=False)  # thứ tự chunk trong tài liệu

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # TABLE: nội dung ở dạng markdown table (giữ cấu trúc hàng-cột),
    # tự thành 1 chunk riêng trọn vẹn, không bị cắt/gộp với văn bản
    # xung quanh - xem app/ingestion/chunker.py để biết lý do.
    content_type: Mapped[str] = mapped_column(String(20), nullable=False, default="TEXT")
    context_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)  # heading/mục gần nhất chứa chunk này
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_solution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="COURSE")

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="chunks")


class Conversation(Base):
    """
    Một phiên hội thoại giữa 1 người dùng và trợ lý AI.

    Gom nhiều `message` (câu hỏi + câu trả lời) lại thành 1 luồng liên
    tục, để AI có "trí nhớ ngắn hạn" trong cùng phiên chat, và để
    người dùng xem lại lịch sử.
    """

    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), nullable=False)
    course_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("course.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """
    Một lượt tin nhắn trong hội thoại - có thể là câu hỏi của người dùng
    (role='user') hoặc câu trả lời của AI (role='assistant').

    citations: lưu dạng JSON danh sách trích dẫn kèm câu trả lời
    (vd: [{"chunk_id": 123, "file": "...", "page": 45}]) - dùng cột
    kiểu Text ở giai đoạn này để đơn giản, có thể nâng lên JSONB thật
    của Postgres khi cần truy vấn sâu vào nội dung trích dẫn.

    category + needs_retrieval: CHỈ có ý nghĩa với message role=
    'assistant' (NULL với role='user') - lưu lại quyết định của Router
    Agent tại THỜI ĐIỂM trả lời, phục vụ thống kê cho Dashboard giảng
    viên (app/instructor/). needs_retrieval=True nhưng citations rỗng
    nghĩa là Hybrid Search KHÔNG tìm thấy tài liệu liên quan nào - đây
    chính là "điểm mù tài liệu" (insufficient_context) theo đặc tả gốc
    Phần 7.3, giá trị thống kê lớn nhất của dashboard: biết CHƯƠNG NÀO
    sinh viên hỏi nhiều mà tài liệu chưa đủ.
    """

    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_message_role"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversation.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    needs_retrieval: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Khái niệm mà câu hỏi này thuộc về (nhận diện tự động bằng so
    # khớp vector, xem app/learning/concept_matcher.py) - NULL nếu
    # không khớp khái niệm nào hoặc lớp chưa có khái niệm.
    #
    # Mục đích: Gap Analysis (app/instructor/) trả lời được câu hỏi
    # "sinh viên hỏi nhiều về CHỦ ĐỀ nào mà tài liệu không đáp ứng
    # được" - cụ thể hơn nhiều so với chỉ biết tỷ lệ % chung chung.
    concept_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("concept.id"), nullable=True
    )

    # Đo lường vận hành - CHỈ ghi cho role='assistant' (NULL với
    # role='user', không có gì để đo ở tin nhắn người dùng gõ).
    #
    # token_usage: JSON {"router": {"in":.., "out":..}, "generate": {...},
    # "embedding_tokens": ..} - đủ chi tiết để tính CHI PHÍ THẬT theo
    # từng bước (xem app/instructor/cost.py), không chỉ tổng gộp.
    #
    # latency_ms: JSON {"guardrail_router_ms":.., "retrieval_ms":..,
    # "generate_ms":.., "total_ms":..} - phục vụ Pipeline Visualization,
    # biết bước nào đang là điểm nghẽn tốc độ bằng SỐ LIỆU THẬT thay vì
    # đoán (đúng bài học từ việc từng đo tốc độ thủ công nhiều lần
    # trước khi có 2 cột này).
    token_usage: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class SecurityLog(Base):
    """
    Nhật ký các lần Guardrail (app/guardrail/) CHẶN 1 nội dung - TÁCH
    RIÊNG khỏi bảng `message` có chủ đích: `message` là lịch sử hội
    thoại HIỂN THỊ CHO USER thấy, còn bảng này là dữ liệu VẬN HÀNH NỘI
    BỘ (chỉ ADMIN xem) - lẫn 2 loại dữ liệu này vào chung 1 bảng sẽ
    khiến lịch sử chat của user bị "rác" bởi những nội dung họ chưa
    từng thấy AI trả lời (vì đã bị chặn từ trước khi tới bước sinh
    câu trả lời).

    Mục đích thực dụng: nếu 1 user liên tục gửi injection/nội dung độc
    hại, ADMIN cần cách phát hiện PATTERN lạm dụng (dò thử phá guardrail
    nhiều lần, tấn công có chủ đích) - không có log này thì không có
    bằng chứng nào để nhận ra hành vi đó đang xảy ra.

    Lưu ý bảo mật: KHÔNG dùng bảng này để tự động khoá tài khoản (đó là
    tính năng riêng, chưa làm ở tác vụ này) - đây chỉ là NHẬT KÝ để con
    người xem xét, tránh việc tự động hoá sai gây khoá nhầm tài khoản
    hợp lệ (vd: học sinh vô tình gõ câu hỏi trùng pattern injection vì
    lý do học thuật thật, không phải tấn công).
    """

    __tablename__ = "security_log"
    __table_args__ = (
        CheckConstraint("direction IN ('input','output')", name="ck_security_log_direction"),
        CheckConstraint("blocked_by IN ('rules','moderation')", name="ck_security_log_blocked_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "input" hoặc "output"
    blocked_by: Mapped[str] = mapped_column(String(20), nullable=False)  # "rules" hoặc "moderation"
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Nội dung gốc bị chặn - lưu lại để ADMIN xem xét bối cảnh thật,
    # không chỉ lý do chung chung. Đây là dữ liệu NHẠY CẢM (có thể
    # chứa nội dung độc hại) - bảng này KHÔNG có endpoint đọc công khai,
    # chỉ dùng cho việc tra cứu trực tiếp trên database khi cần điều tra.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Concept(Base):
    """
    Một "khái niệm" học thuật thuộc 1 môn (vd: "Recursion", "Tuple") -
    nền tảng cho Learning Assistant (quiz + theo dõi mức độ nắm vững).

    GIỚI HẠN CÓ CHỦ Ý ở giai đoạn này: concept do GIẢNG VIÊN tự tạo tay
    qua API, KHÔNG tự động trích xuất từ tài liệu bằng AI - việc trích
    xuất tự động là công việc của 1 "Curator Agent" riêng (chưa làm),
    tốn thêm 1 lượt gọi LLM cho mỗi chunk và cần có bước duyệt riêng.
    Tạo tay là hạn chế thực tế thật (giảng viên phải nhớ tự thêm), đổi
    lấy việc không phải xây thêm 1 pipeline AI mới ở giai đoạn MVP này.

    complexity: độ khó 1-5, GIẢNG VIÊN tự đánh giá (chủ quan) - dùng
    làm "giá trị khởi điểm" hợp lý hơn con số cố định cho mọi khái niệm
    khi CHƯA có đủ dữ liệu tương tác thật (xem StudentMastery).
    """

    __tablename__ = "concept"
    __table_args__ = (
        CheckConstraint("complexity BETWEEN 1 AND 5", name="ck_concept_complexity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    course_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("course.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    complexity: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Vector ngữ nghĩa của TÊN khái niệm - tính ĐÚNG 1 LẦN lúc giảng
    # viên tạo khái niệm (lúc đó không người dùng nào phải chờ), để khi
    # sinh viên chat, việc "câu hỏi này thuộc khái niệm nào" chỉ còn là
    # phép nhân vector TRONG BỘ NHỚ với vector câu hỏi (vốn đã được
    # tính sẵn cho Hybrid Search) - KHÔNG tốn thêm lượt gọi API nào,
    # không thêm mili giây nào vào thời gian người dùng chờ.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)


class StudentMastery(Base):
    """
    Mức độ nắm vững 1 concept của 1 sinh viên - dùng chiến lược
    HEURISTIC (đếm streak trả lời đúng liên tiếp), KHÔNG PHẢI BKT thật
    (Bayesian Knowledge Tracing với tham số fit bằng EM).

    LÝ DO KHÔNG DÙNG BKT NGAY: BKT cần fit tham số riêng cho từng
    concept từ dữ liệu tương tác THẬT (khuyến nghị ≥2000 lượt quan sát
    để tham số có ý nghĩa thống kê, tránh hội tụ về "degenerate
    parameters" vô nghĩa sư phạm) - dự án hiện chưa có bất kỳ lượt
    tương tác quiz nào (giai đoạn "cold start" hoàn toàn). Heuristic
    đơn giản, minh bạch, đủ dùng cho tới khi đủ dữ liệu thật.

    streak: số câu ĐÚNG liên tiếp gần nhất (reset về 0 nếu trả lời sai)
    mastered: đạt True khi streak >= 3 (ngưỡng cố định, đơn giản)
    """

    __tablename__ = "student_mastery"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), primary_key=True)
    concept_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("concept.id"), primary_key=True)
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_obs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mastered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuizQuestion(Base):
    """
    1 câu hỏi trắc nghiệm cho 1 concept - sinh bằng LLM (gpt-4o-mini)
    từ nội dung chunk thuộc concept đó, rồi LƯU LẠI (cache) để tái
    dùng cho các lượt quiz sau, thay vì gọi LLM sinh mới mỗi lần.

    Đánh đổi đã chốt: tiết kiệm chi phí LLM đáng kể khi nhiều sinh
    viên cùng làm quiz 1 concept, đổi lại 1 sinh viên làm quiz nhiều
    lần có thể gặp lại câu hỏi cũ (chấp nhận được cho MVP - có thể
    thêm "sinh thêm câu mới" sau nếu 1 concept có quá ít câu hỏi).

    options: lưu dạng JSON string (giống Message.citations) - danh
    sách 4 lựa chọn, vd ["A. ...", "B. ...", "C. ...", "D. ..."].
    correct_index: vị trí đáp án đúng trong options (0-3).
    """

    __tablename__ = "quiz_question"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    concept_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("concept.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list[str], 4 phần tử
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Assignment(Base):
    """
    Một bài tập giảng viên giao cho cả lớp (Tác vụ #13).

    THIẾT KẾ TÁI SỬ DỤNG: bài tập KHÔNG có kho câu hỏi riêng - nó tham
    chiếu tới chính QuizQuestion đã sinh sẵn cho từng khái niệm (xem
    bảng assignment_question bên dưới). Nhờ vậy: câu hỏi đã cache được
    dùng lại (không tốn thêm lượt gọi LLM), và điểm số bài tập cũng
    cập nhật vào cùng hệ thống mastery như quiz tự luyện.

    due_at: hạn nộp. NULL = không giới hạn thời gian.
    """

    __tablename__ = "assignment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    course_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("course.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssignmentQuestion(Base):
    """
    Liên kết 1 bài tập với 1 câu hỏi cụ thể, kèm thứ tự hiển thị.

    Bảng trung gian (many-to-many) thay vì nhét danh sách id vào 1 cột
    JSON: cho phép truy vấn ngược ("câu hỏi này thuộc những bài tập
    nào") và đảm bảo toàn vẹn dữ liệu bằng khoá ngoại thật.
    """

    __tablename__ = "assignment_question"

    assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assignment.id"), primary_key=True
    )
    quiz_question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quiz_question.id"), primary_key=True
    )
    ord: Mapped[int] = mapped_column(Integer, nullable=False)  # thứ tự câu hỏi trong bài


class AssignmentSubmission(Base):
    """
    Một lượt sinh viên nộp bài - LƯU ĐIỂM ĐÃ CHẤM, không lưu từng câu
    trả lời (từng câu đã có trong quiz_attempt, tra được qua user_id +
    quiz_question_id nếu cần xem chi tiết).

    Khoá chính CẶP (assignment_id, user_id): mỗi sinh viên chỉ nộp 1
    lần cho mỗi bài - ràng buộc ở tầng database, không dựa vào việc
    tầng ứng dụng "nhớ" kiểm tra.
    """

    __tablename__ = "assignment_submission"

    assignment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assignment.id"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), primary_key=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # số câu đúng
    total: Mapped[int] = mapped_column(Integer, nullable=False)  # tổng số câu
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuizAttempt(Base):
    """
    1 lượt sinh viên trả lời 1 QuizQuestion - lịch sử thô, dùng để suy
    ra StudentMastery (không phải nguồn dữ liệu chính user đọc trực
    tiếp, tương tự quan hệ SecurityLog/Message: đây là log vận hành).
    """

    __tablename__ = "quiz_attempt"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), nullable=False)
    quiz_question_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("quiz_question.id"), nullable=False)
    selected_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRun(Base):
    """
    Một lượt chạy scripts/eval.py - lưu vào DB thay vì chỉ ghi ra file
    JSON cục bộ (eval_report.json cũ), để xem được XU HƯỚNG chất lượng
    qua thời gian trên Eval Dashboard, không mất lịch sử khi máy dev
    chạy lại hoặc đổi máy.

    git_commit_hash: SHA của commit đang chạy lúc eval - PHỤC VỤ ĐIỀU
    TRA khi thấy điểm số tụt xuống ("chất lượng giảm từ commit nào?").
    NULL nếu chạy ở trạng thái working tree chưa commit hoặc không xác
    định được (không chặn eval chỉ vì thiếu git).

    model_version / dataset_version: model LLM đang dùng (Router/Academic
    Agent) và version của bộ câu hỏi mẫu (eval_dataset.json) - cần thiết
    để so sánh ĐÚNG, tránh hiểu nhầm 1 điểm số tụt là do code tệ đi
    trong khi thực ra do đổi model hoặc đổi bộ câu hỏi.

    KHÔNG có endpoint xoá EvalRun (xem app/instructor/eval_router.py) -
    giữ lại toàn bộ lịch sử để xem xu hướng dài hạn, kể cả lượt chạy có
    điểm thấp (đặc biệt hữu ích để so sánh trước/sau 1 lần sửa lỗi).
    """

    __tablename__ = "eval_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    git_commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(50), nullable=False)

    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, nullable=False)
    category_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    avg_recall_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_cases_scored: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case_results: Mapped[list["EvalCaseResult"]] = relationship(
        back_populates="eval_run", cascade="all, delete-orphan"
    )


class EvalCaseResult(Base):
    """
    Kết quả chi tiết CỦA TỪNG câu hỏi mẫu trong 1 EvalRun - lưu cả
    judge_reasoning THÔ (câu giải thích của LLM-judge, không rút gọn)
    để giảng viên/admin đọc lại được LÝ DO cụ thể đằng sau 1 điểm số,
    không chỉ con số trần trụi (vd "3/5" không tự giải thích được TẠI
    SAO chỉ 3, nhưng judge_reasoning thì có).
    """

    __tablename__ = "eval_case_result"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    eval_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("eval_run.id"), nullable=False)

    case_id: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_category: Mapped[str] = mapped_column(String(50), nullable=False)
    actual_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recall_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    judge_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    eval_run: Mapped["EvalRun"] = relationship(back_populates="case_results")
