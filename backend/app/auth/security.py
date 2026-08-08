"""
Hai việc cốt lõi của bảo mật đăng nhập: BĂM MẬT KHẨU và JWT (vé đăng nhập).

Không tự chế thuật toán - dùng đúng 2 thư viện chuẩn ngành (passlib,
python-jose). Tự viết lại logic mã hoá là một trong những lỗi bảo mật
phổ biến nhất, vì rất dễ bỏ sót một chi tiết nhỏ mà kẻ tấn công khai
thác được.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# CryptContext quản lý việc băm/kiểm tra mật khẩu bằng bcrypt.
#
# "bcrypt" cố tình CHẬM (mất khoảng 100-300ms để băm 1 mật khẩu) - đây
# không phải nhược điểm mà là tính năng bảo mật: nếu database bị đánh
# cắp, kẻ tấn công muốn dò ra mật khẩu gốc bằng cách thử hàng triệu khả
# năng sẽ tốn cực nhiều thời gian, khác hẳn thuật toán băm nhanh như
# SHA-256 (dùng cho việc khác, KHÔNG được dùng để băm mật khẩu).
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Băm mật khẩu gốc thành chuỗi lưu vào cột password_hash."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    Kiểm tra mật khẩu người dùng vừa nhập có khớp với bản băm đã lưu
    không - KHÔNG bao giờ giải mã ngược password_hash để so sánh (vì
    bcrypt là băm một chiều, không giải mã được), mà băm lại mật khẩu
    vừa nhập theo đúng cách rồi so sánh 2 chuỗi băm.
    """
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(user_id: int, role: str) -> str:
    """
    Tạo JWT - "vé đăng nhập có chữ ký chống giả mạo".

    Bên trong vé (gọi là "payload") chứa:
    - sub (subject): user_id, để biết vé này của ai
    - role: vai trò, để mọi API sau đó không cần tra lại DB mới biết
      user có quyền gì
    - exp (expiry): thời điểm hết hạn - qua giờ này vé không còn hợp lệ

    Toàn bộ payload được "ký" bằng jwt_secret (chuỗi bí mật chỉ backend
    biết) - nếu ai đó cố sửa role trong vé, chữ ký sẽ không khớp nữa và
    server phát hiện được ngay khi giải mã.
    """
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "role": role, "exp": expire_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """
    Giải mã + xác minh chữ ký của 1 JWT.

    Trả về None nếu: chữ ký sai (vé giả/bị sửa), hoặc vé đã hết hạn.
    Đây là hàm mà `app/auth/dependencies.py` sẽ gọi ở MỌI request cần
    biết "ai đang gọi API này".
    """
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
