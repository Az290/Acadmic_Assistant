"""
Định nghĩa "hình dạng" dữ liệu ra/vào cho các API auth, bằng Pydantic.

Vì sao cần lớp này thay vì dùng thẳng model database (AppUser) làm
request/response: model database có cột `password_hash` - tuyệt đối
không được để lọt ra ngoài response (dù đã băm, vẫn không nên phơi ra).
Pydantic schema là "bộ lọc" tường minh, chỉ khai báo đúng những trường
được phép đi qua API.

FastAPI dùng các class này để: (1) tự động kiểm tra dữ liệu client gửi
lên có đúng định dạng không (vd: email phải đúng định dạng email) - sai
sẽ tự trả lỗi 422 rõ ràng mà không cần code tay; (2) tự sinh tài liệu
API tương tác tại /docs.
"""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Tối thiểu 8 ký tự")
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ResetPasswordRequest(BaseModel):
    target_email: EmailStr  # email của học sinh cần reset


class ResetPasswordResponse(BaseModel):
    target_email: str
    temporary_password: str  # giáo viên đọc/gửi tay cho học sinh


class UserPublic(BaseModel):
    """Thông tin user được phép trả ra ngoài - KHÔNG có password_hash."""

    id: int
    email: str
    full_name: str
    role: str

    model_config = {"from_attributes": True}  # cho phép tạo trực tiếp từ object AppUser
