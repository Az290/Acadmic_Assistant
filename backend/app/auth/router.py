"""
5 endpoint xử lý đăng nhập/đăng ký/quên mật khẩu (Tác vụ #3).

APIRouter: cách FastAPI cho phép chia API thành nhiều "router" nhỏ theo
chủ đề (auth, courses...) rồi gắn hết vào app chính ở main.py - giữ
main.py gọn, mỗi file chỉ lo 1 nhóm chức năng.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    UserPublic,
)
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.models import AppUser
from app.db.session import get_db

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# Tên cookie lưu JWT - dùng chung 1 hằng số để tránh gõ sai chuỗi ở
# nhiều chỗ (login đặt cookie, logout xoá cookie, dependencies đọc cookie).
COOKIE_NAME = "access_token"


def _set_auth_cookie(response: Response, token: str) -> None:
    """
    Đặt JWT vào HttpOnly Cookie - lựa chọn đã chốt để chống đánh cắp
    token qua lỗi XSS (JavaScript trên trang KHÔNG đọc được cookie này,
    kể cả khi có mã độc chèn vào trang).
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,       # JavaScript không đọc được
        secure=True,          # chỉ gửi qua HTTPS (production luôn dùng HTTPS)
        samesite="lax",       # chống một dạng tấn công CSRF cơ bản
        max_age=60 * 60 * 24 * 7,  # 7 ngày - khớp với jwt_expire_minutes mặc định
    )


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db)):
    """
    Đăng ký tài khoản mới - role mặc định luôn là STUDENT.

    Vì sao không cho client tự chọn role khi đăng ký: nếu cho phép,
    bất kỳ ai cũng có thể tự đăng ký làm "INSTRUCTOR" hoặc "ADMIN" -
    lỗ hổng phân quyền nghiêm trọng. Việc nâng quyền (vd: cấp quyền
    giáo viên) phải qua một kênh riêng do ADMIN thực hiện, không có
    trong tác vụ này.
    """
    existing = await session.execute(select(AppUser).where(AppUser.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email này đã được đăng ký."
        )

    user = AppUser(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role="STUDENT",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login", response_model=UserPublic)
async def login(body: LoginRequest, response: Response, session: AsyncSession = Depends(get_db)):
    """
    Đăng nhập - kiểm tra email/mật khẩu, nếu đúng thì phát JWT vào cookie.

    Lưu ý bảo mật: dù sai email hay sai mật khẩu, ta trả về CÙNG một
    thông báo lỗi chung chung ("Email hoặc mật khẩu không đúng").
    Không nói rõ "email không tồn tại" - nếu nói rõ, kẻ tấn công có thể
    dò xem email nào đã đăng ký trong hệ thống (rò rỉ thông tin qua
    kênh phụ - cùng nguyên tắc đã áp dụng ở tầng ACL của Tác vụ #2).
    """
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc mật khẩu không đúng."
    )

    result = await session.execute(select(AppUser).where(AppUser.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise invalid_credentials

    token = create_access_token(user_id=user.id, role=user.role)
    _set_auth_cookie(response, token)
    return user


@router.post("/logout")
async def logout(response: Response):
    """Xoá cookie - từ request tiếp theo, get_current_user sẽ không tìm thấy token nữa."""
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Đã đăng xuất."}


@router.get("/me", response_model=UserPublic)
async def get_me(user: AppUser = Depends(get_current_user)):
    """
    Trả thông tin + role của người đang đăng nhập.

    Đây là endpoint FRONTEND SẼ GỌI NGAY SAU KHI ĐĂNG NHẬP để biết
    role và điều hướng đúng giao diện (student/instructor/admin) -
    đúng yêu cầu "vào web gặp đăng nhập ngay, sau đó vào thẳng giao
    diện riêng theo role" đã thống nhất.
    """
    return user


@router.post("/admin/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db),
    _actor: AppUser = Depends(require_role("ADMIN", "INSTRUCTOR")),
):
    """
    Giáo viên/Admin reset mật khẩu giúp một học sinh - đây là giải pháp
    "quên mật khẩu" đã chốt cho giai đoạn này (KHÔNG gửi email OTP, để
    tránh phải thêm hạ tầng gửi email khi quy mô còn nhỏ).

    Luồng dùng thực tế: học sinh báo quên mật khẩu cho giáo viên (ngoài
    đời/nhắn tin) -> giáo viên gọi API này với email học sinh -> hệ
    thống sinh 1 mật khẩu tạm ngẫu nhiên, trả về cho giáo viên đọc/gửi
    lại cho học sinh -> học sinh đăng nhập bằng mật khẩu tạm này.

    _actor: biến này CHỈ dùng để bắt buộc FastAPI chạy dependency
    require_role trước khi vào hàm - bản thân không dùng tới giá trị
    của nó nên đặt tên có dấu gạch dưới đầu (quy ước Python cho "khai
    báo nhưng cố tình không dùng").
    """
    result = await session.execute(select(AppUser).where(AppUser.email == body.target_email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy học sinh với email này.")

    # secrets.token_urlsafe: sinh chuỗi ngẫu nhiên an toàn về mật mã học
    # (khác hẳn random.choice thông thường - không đoán trước được).
    temporary_password = secrets.token_urlsafe(9)  # ví dụ: "kJ8x_2mQpL7w"
    user.password_hash = hash_password(temporary_password)
    await session.commit()

    return ResetPasswordResponse(target_email=user.email, temporary_password=temporary_password)
