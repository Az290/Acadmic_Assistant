"""add system_knowledge table

System Knowledge Base cho phép Agent tra loi cau hoi ve CACH HE THONG
hoat dong (khong phai noi dung mon hoc).

Seed data bao gom:
- ENROLLMENT: join lop, xem khoa hoc
- QUIZ: lam quiz, xem diem, mastery
- DOCUMENT: upload, xem tai lieu
- PERMISSION: quyen han
"""

from alembic import op
import sqlalchemy as sa

revision = "20260823_0018"
down_revision = "20260811_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_knowledge",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("keyword", sa.String(100), nullable=False, index=True),
        sa.Column("question_pattern", sa.Text(), nullable=False),
        sa.Column("default_answer", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, index=True),
        sa.Column("api_endpoint", sa.String(200), nullable=True),
        sa.Column("response_template", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Seed data - hardcode values to avoid parameter issues
    op.execute("""
        INSERT INTO system_knowledge (keyword, question_pattern, default_answer, category, api_endpoint, response_template, priority, is_active) VALUES
        ('enroll', '(lam sao|muon).{0,20}join.{0,20}(lop|class)', 'Sinh vien khong tu vao lop duoc. Chi giang vien moi them duoc sinh vien vao lop.', 'ENROLLMENT', NULL, NULL, 10, true),
        ('enroll', '(lam sao|muon).{0,20}(vao|tham gia).{0,20}(lop|class)', 'Ban khong the tu dang ky vao lop. Giang vien se them ban vao lop bang email.', 'ENROLLMENT', NULL, NULL, 11, true),
        ('quiz', '(lam sao|muon).{0,20}quiz', 'De lam quiz, ban can duoc them vao lop hoc truoc.', 'QUIZ', NULL, NULL, 10, true),
        ('quiz', '(tai sao|why|vi sao).{0,20}(khong|lam|duoc).{0,20}quiz', 'Ban khong the lam quiz vi chua duoc them vao lop hoc nao.', 'QUIZ', NULL, NULL, 11, true),
        ('quiz', '(diem|ket qua).{0,20}quiz', 'Ket qua quiz cua ban phu thuoc vao so cau tra loi dung tren tong so cau.', 'QUIZ', NULL, NULL, 20, true),
        ('mastery', '(nam|vung|nao|kien thuc|tien do)', 'Muc do nam vung (mastery) cho biet ban da hieu bao nhieu phan tram noi dung.', 'QUIZ', NULL, NULL, 25, true),
        ('on', '(on|review|practice|luyen).{0,30}(bai|quiz|kien thuc)', 'Ban co the on tap bang cach lam quiz hoac hoi Nova.', 'QUIZ', NULL, NULL, 30, true),
        ('tai lieu', '(lam sao|muon|cach).{0,20}(upload|dang|dong gop).{0,20}(tai lieu|pdf)', 'Ban co the dong gop tai lieu bang cach vao trang tai lieu va nhan Upload.', 'DOCUMENT', NULL, NULL, 10, true),
        ('tai lieu', '(xem|tim|doc).{0,20}(tai lieu|pdf)', 'Ban co the xem tai lieu da duoc duyet trong trang Tai lieu cua lop hoc.', 'DOCUMENT', NULL, NULL, 20, true),
        ('duyet', '(tai lieu).{0,20}(cho|dang|pending).{0,20}(duyet|review)', 'Tai lieu ban dong gop se o trang thai ''Cho duyet'' cho den khi giang vien phe duyet.', 'DOCUMENT', NULL, NULL, 30, true),
        ('quyen', '(quyen|han|duoc lam|khong duoc|gioi han)', 'Quyen han phu thuoc vao vai tro: Sinh vien co the hoi dap, lam quiz, dong gop tai lieu.', 'PERMISSION', NULL, NULL, 10, true),
        ('giang vien', '(giang vien|gv|instructor).{0,30}(xem|thay|kiem).{0,20}(cau hoi|chat|noi dung)', 'Giang vien KHONG xem duoc noi dung cau hoi/chat cua ban. Ho chi thay so lieu tong hop.', 'PERMISSION', NULL, NULL, 20, true),
        ('rieng tu', '(rieng tu|privacy|bao mat|an toan)', 'Noi dung cau hoi cua ban la rieng tu. Giang vien chi thay so lieu thong ke.', 'PERMISSION', NULL, NULL, 30, true)
    """)


def downgrade() -> None:
    op.drop_table("system_knowledge")
