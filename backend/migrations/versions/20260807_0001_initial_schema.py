"""initial schema: course, app_user, document, chunk, conversation, message

Đây là migration đầu tiên - "ảnh chụp" cấu trúc database ban đầu.

Alembic quản lý các thay đổi schema giống Git quản lý code: mỗi lần
sửa cấu trúc bảng (thêm cột, thêm bảng...), ta tạo 1 file migration
mới, có thể "revision_id" liên kết tới migration trước đó. Nhờ vậy
lúc nào cũng biết chính xác DB đang ở "phiên bản" nào, và có thể lùi
lại (downgrade) nếu một thay đổi gây lỗi.

Migration này viết THỦ CÔNG (không dùng autogenerate) vì lúc viết
chưa có Postgres thật để Alembic so sánh - nhưng nội dung phản ánh
đúng 100% các bảng đã định nghĩa trong app/db/models.py.
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# Alembic cần 2 định danh này để biết migration này là gì và nối tiếp cái nào
revision = "20260807_0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536  # khớp với app/db/models.py


def upgrade() -> None:
    # Bật tiện ích mở rộng pgvector - PHẢI chạy trước khi tạo cột kiểu
    # Vector. Đây là bước "cài thêm khả năng lưu & tìm vector" vào
    # chính Postgres, không phải một dịch vụ tách biệt.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "course",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "app_user",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('STUDENT','INSTRUCTOR','ADMIN')", name="ck_app_user_role"),
    )

    op.create_table(
        "document",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("course_id", sa.BigInteger(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("license_status", sa.String(20), nullable=False, server_default="RESTRICTED"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("uploaded_by", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "license_status IN ('OWNED','LICENSED','OPEN','RESTRICTED')",
            name="ck_document_license_status",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PROCESSING','PENDING_REVIEW','APPROVED','REJECTED','ARCHIVED')",
            name="ck_document_status",
        ),
    )

    op.create_table(
        "chunk",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("document.id"), nullable=False),
        sa.Column("course_id", sa.BigInteger(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_prefix", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("is_solution", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="COURSE"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("embedding_version", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "visibility IN ('PUBLIC','COURSE','INSTRUCTOR_ONLY')", name="ck_chunk_visibility"
        ),
    )

    # Index HNSW cho tìm kiếm vector gần đúng - tăng tốc truy vấn
    # "top-K đoạn văn gần nghĩa nhất" từ chậm (quét toàn bộ bảng) thành
    # nhanh (chỉ dò một phần cấu trúc đồ thị đã dựng sẵn). Giải thích
    # trực quan có trong learning-log.html Bài 2.
    op.execute(
        "CREATE INDEX chunk_embedding_hnsw ON chunk "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # Index thường cho các cột hay dùng để LỌC QUYỀN TRUY CẬP (ACL) -
    # đây là câu điều kiện chạy trên MỌI truy vấn tìm kiếm, nên cần
    # nhanh ngay từ đầu, không đợi tối ưu sau.
    op.create_index("ix_chunk_acl", "chunk", ["course_id", "visibility", "is_solution"])

    op.create_table(
        "conversation",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("course_id", sa.BigInteger(), sa.ForeignKey("course.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "message",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "conversation_id", sa.BigInteger(), sa.ForeignKey("conversation.id"), nullable=False
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_message_role"),
    )


def downgrade() -> None:
    # Thứ tự XÓA ngược lại thứ tự TẠO - vì các bảng con (vd: message)
    # tham chiếu tới bảng cha (conversation) qua ForeignKey, phải xóa
    # bảng con trước để không vi phạm ràng buộc khóa ngoại.
    op.drop_table("message")
    op.drop_table("conversation")
    op.drop_index("ix_chunk_acl", table_name="chunk")
    op.execute("DROP INDEX IF EXISTS chunk_embedding_hnsw")
    op.drop_table("chunk")
    op.drop_table("document")
    op.drop_table("app_user")
    op.drop_table("course")
