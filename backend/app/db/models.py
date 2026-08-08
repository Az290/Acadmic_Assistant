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
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("document.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("course.id"), nullable=False)
    ord: Mapped[int] = mapped_column(Integer, nullable=False)  # thứ tự chunk trong tài liệu

    content: Mapped[str] = mapped_column(Text, nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
