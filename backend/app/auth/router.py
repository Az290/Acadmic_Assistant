"""
Endpoint xử lý đăng nhập/đăng ký/quên mật khẩu + refresh token rotation.

APIRouter: cách FastAPI cho phép chia API thành nhiều "router" nhỏ theo
chủ đề (auth, courses...) rồi gắn hết vào app chính ở main.py - giữ
main.py gọn, mỗi file chỉ lo 1 nhóm chức năng.
"""

import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.refresh import RefreshTokenError, issue_refresh_token, revoke_all_refresh_tokens, rotate_refresh_token
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
from app.rate_limit import LOGIN_RATE_LIMIT, limiter

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# Tên 2 cookie - TÁCH RIÊNG access token và refresh token, mỗi loại
# có vòng đời khác nhau và mục đích khác nhau (xem giải thích chi tiết
# trong app/auth/refresh.py).
ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"


def _set_access_cookie(response: Response, token: str) -> None:
    """
    Đặt access token (JWT) vào HttpOnly Cookie - dùng cho MỌI request
    thường ngày. Sống NGẮN (30 phút, xem config.py) - hết hạn thì
    frontend tự gọi /v1/auth/refresh để xin cái mới, KHÔNG bắt user
    đăng nhập lại bằng mật khẩu.
    """
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        httponly=True,       # JavaScript không đọc được
        secure=True,          # chỉ gửi qua HTTPS (production luôn dùng HTTPS)
        samesite="lax",       # chống một dạng tấn công CSRF cơ bản
        max_age=30 * 60,      # 30 phút - khớp jwt_expire_minutes
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    """
    Đặt refresh token vào 1 cookie RIÊNG - sống dài hơn nhiều (7 ngày).

    path="/v1/auth" (khác access cookie - áp dụng toàn site): refresh
    token CHỈ CẦN gửi kèm khi gọi các endpoint auth (login, refresh,
    logout) - không cần gửi kèm ở MỌI request khác, giảm thiểu bề mặt
    có thể bị lộ nếu 1 endpoint nào đó có lỗ hổng khác trong tương lai.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 ngày - khớp refresh_token_expire_days
        path="/v1/auth",
    )


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, refresh_token)


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(LOGIN_RATE_LIMIT)  # cùng ngưỡng chặt với login - chống tạo tài khoản ảo hàng loạt
async def register(request: Request, body: RegisterRequest, session: AsyncSession = Depends(get_db)):
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
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(
    request: Request, body: LoginRequest, response: Response, session: AsyncSession = Depends(get_db)
):
    """
    Đăng nhập - kiểm tra email/mật khẩu, nếu đúng thì phát JWT vào cookie.

    Lưu ý bảo mật: dù sai email hay sai mật khẩu, ta trả về CÙNG một
    thông báo lỗi chung chung ("Email hoặc mật khẩu không đúng").
    Không nói rõ "email không tồn tại" - nếu nói rõ, kẻ tấn công có thể
    dò xem email nào đã đăng ký trong hệ thống (rò rỉ thông tin qua
    kênh phụ - cùng nguyên tắc đã áp dụng ở tầng ACL truy vấn tài liệu).

    @limiter.limit(LOGIN_RATE_LIMIT): giới hạn 5 lần/phút theo địa chỉ
    IP để chống brute-force dò mật khẩu hàng loạt. Tham số
    `request: Request` là yêu cầu bắt buộc của slowapi để nó đọc được
    địa chỉ IP người gọi.
    """
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc mật khẩu không đúng."
    )

    result = await session.execute(select(AppUser).where(AppUser.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise invalid_credentials

    access_token = create_access_token(user_id=user.id, role=user.role)
    refresh_token = await issue_refresh_token(session, user.id)
    _set_auth_cookies(response, access_token, refresh_token)
    return user


@router.post("/refresh", response_model=UserPublic)
async def refresh_access_token(
    response: Response,
    session: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
):
    """
    Xin cấp access token MỚI bằng refresh token, KHÔNG cần gõ lại mật khẩu.

    Frontend sẽ tự động gọi endpoint này khi 1 request khác trả về 401
    (access token hết hạn) - nếu refresh thành công, thử lại request
    ban đầu; nếu refresh cũng thất bại (refresh token hết hạn/bị thu
    hồi), mới thật sự bắt user quay lại trang đăng nhập.
    """
    if refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Không tìm thấy refresh token.")

    try:
        user_id, new_refresh_token = await rotate_refresh_token(session, refresh_token)
    except RefreshTokenError:
        # Không tiết lộ lý do cụ thể (hết hạn/bị thu hồi/không tồn tại)
        # ra ngoài - cùng nguyên tắc "không rò rỉ qua kênh phụ" như login.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.",
        )

    result = await session.execute(select(AppUser).where(AppUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn tồn tại.")

    new_access_token = create_access_token(user_id=user.id, role=user.role)
    _set_auth_cookies(response, new_access_token, new_refresh_token)
    return user


@router.post("/logout")
async def logout(
    response: Response,
    session: AsyncSession = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    """
    Đăng xuất - xoá cả 2 cookie VÀ thu hồi mọi refresh token còn hiệu
    lực của user. Đăng xuất có nghĩa THẬT SỰ: kể cả ai đó đang giữ
    refresh token cũ (vd: đã sao chép trước đó), token đó cũng không
    dùng được nữa ngay lập tức, không chỉ xoá cookie trên trình duyệt
    hiện tại.
    """
    await revoke_all_refresh_tokens(session, user.id)
    response.delete_cookie(ACCESS_COOKIE_NAME)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/v1/auth")
    return {"message": "Đã đăng xuất."}


@router.get("/me", response_model=UserPublic)
async def get_me(user: AppUser = Depends(get_current_user)):
    """
    Trả thông tin + role của người đang đăng nhập.

    Đây là endpoint frontend sẽ gọi ngay sau khi đăng nhập để biết
    role và điều hướng đúng giao diện (student/instructor/admin).
    """
    return user


@router.post("/admin/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db),
    _actor: AppUser = Depends(require_role("ADMIN", "INSTRUCTOR")),
):
    """
    Giáo viên/Admin reset mật khẩu giúp một học sinh - giải pháp "quên
    mật khẩu" không cần gửi email OTP, tránh phải thêm hạ tầng gửi
    email khi quy mô còn nhỏ.

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
