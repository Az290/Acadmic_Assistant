"""
"Người gác cổng" cho các API cần biết ai đang gọi, và họ có quyền gì.

FastAPI có khái niệm "Dependency" - một hàm được khai báo là tham số
mặc định của endpoint, FastAPI tự động chạy nó TRƯỚC KHI vào phần thân
endpoint. Cùng khuôn mẫu này cũng được dùng cho `get_db` (cấp session
DB, xem app/db/session.py) - ở đây áp dụng cho việc xác thực người dùng.

Có 2 tầng dependency:
1. get_current_user   - "bạn là ai?" (đọc JWT từ cookie, tra ra user)
2. require_role(...)   - "bạn có quyền này không?" (kiểm tra role)

Vì sao chặn quyền ở TẦNG BACKEND (không chỉ ẩn nút trên giao diện):
ẩn nút chỉ ảnh hưởng những gì user THẤY, nhưng ai cũng có thể tự gọi
thẳng vào API bằng công cụ khác (Postman, curl...) nếu backend không
tự kiểm tra. Đây là nguyên tắc "không tin tưởng phía client".
"""

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.db.models import AppUser
from app.db.session import get_db


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_db),
) -> AppUser:
    """
    Đọc JWT từ HttpOnly Cookie tên "access_token", xác minh chữ ký,
    rồi tra ra đúng người dùng trong database.

    Vì sao tra lại DB thay vì chỉ tin nội dung trong token: token có
    thể chứa thông tin CŨ nếu user đã bị khoá tài khoản/đổi role sau
    khi token được phát hành. Với quy mô dự án này (chưa cần tối ưu
    tới mức bỏ qua 1 lần tra DB), an toàn hơn vẫn ưu tiên hơn.

    Nếu không có cookie, cookie hỏng, hoặc user không tồn tại nữa ->
    trả lỗi 401 (Unauthorized) - FastAPI tự động biến exception này
    thành response lỗi đúng chuẩn HTTP cho client.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Chưa đăng nhập hoặc phiên đăng nhập đã hết hạn.",
    )

    if access_token is None:
        raise unauthorized

    payload = decode_access_token(access_token)
    if payload is None:
        raise unauthorized

    user_id = int(payload["sub"])
    result = await session.execute(select(AppUser).where(AppUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized

    return user


def require_role(*allowed_roles: str):
    """
    "Nhà máy" tạo ra dependency kiểm tra role - dùng như sau trong 1
    endpoint:

        @app.post("/v1/courses")
        async def create_course(user: AppUser = Depends(require_role("INSTRUCTOR"))):
            ...

    Nếu user đã đăng nhập nhưng role không nằm trong danh sách cho
    phép -> trả lỗi 403 (Forbidden - "biết bạn là ai rồi, nhưng bạn
    không được phép làm việc này"), khác với 401 (Unauthorized -
    "chưa biết bạn là ai").
    """

    async def checker(user: AppUser = Depends(get_current_user)) -> AppUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Chức năng này chỉ dành cho: {', '.join(allowed_roles)}.",
            )
        return user

    return checker
