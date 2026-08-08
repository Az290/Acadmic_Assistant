"""
Quản lý Refresh Token - logic cần truy vấn database, tách riêng khỏi
security.py (module đó thuần thuật toán mã hoá, không chạm DB).
"""

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import generate_refresh_token, hash_refresh_token
from app.config import get_settings
from app.db.models import RefreshToken

settings = get_settings()

# Khoảng thời gian sau khi 1 refresh token bị rotate, trong đó việc
# dùng lại CHÍNH token đó vẫn được coi là hợp lệ (không phải dấu hiệu
# bị đánh cắp). Cần thiết vì nhiều request có thể vô tình cùng gọi
# refresh song song (nhiều tab/thành phần trang cùng phát hiện access
# token hết hạn gần như đồng thời) - nếu không có khoảng này, các
# request đến sau request đầu tiên vài mili-giây sẽ bị hiểu nhầm là
# tấn công và bị đăng xuất oan.
REUSE_GRACE_PERIOD_SECONDS = 10

# Cache TRONG BỘ NHỚ (không lưu DB): ánh xạ hash của token VỪA bị
# rotate -> (token gốc mới đã phát ra thay thế, thời điểm hết hạn cache).
#
# Vì sao không lưu token gốc vào database, kể cả tạm thời: refresh
# token gốc là bí mật có thể dùng để đăng nhập - lưu nó dưới bất kỳ
# hình thức đọc được nào vào DB (dù có tự xoá sau 10 giây) làm giảm ý
# nghĩa của việc băm token trước khi lưu. Cache RAM không có rủi ro
# này vì không nằm trong bản backup/dump database.
#
# Giới hạn CẦN BIẾT: cache này chỉ đúng khi backend chạy ĐÚNG 1
# instance. Nếu sau này chạy nhiều instance song song (scale ngang),
# 1 request có thể rơi vào instance không có cache này trong bộ nhớ -
# lúc đó cần chuyển sang lưu trữ dùng chung (vd: Redis) thay vì dict
# trong process, cùng lúc với việc nâng cấp rate limiting (app/rate_limit.py)
# vì 2 module này có chung giới hạn "chỉ đúng với 1 instance".
_reuse_cache: dict[str, tuple[str, float]] = {}


def _remember_replacement(old_token_hash: str, new_raw_token: str) -> None:
    _reuse_cache[old_token_hash] = (new_raw_token, time.monotonic() + REUSE_GRACE_PERIOD_SECONDS)


def _recall_replacement(old_token_hash: str) -> str | None:
    entry = _reuse_cache.get(old_token_hash)
    if entry is None:
        return None
    new_raw_token, expires_at = entry
    if time.monotonic() > expires_at:
        del _reuse_cache[old_token_hash]
        return None
    return new_raw_token


async def issue_refresh_token(session: AsyncSession, user_id: int) -> str:
    """
    Tạo 1 refresh token mới cho user, lưu bản băm vào DB, trả về token
    gốc (chưa băm) để gửi cho client qua cookie - đây là lần duy nhất
    token gốc tồn tại dưới dạng có thể đọc được, sau đó chỉ còn bản
    băm trong DB.
    """
    raw_token = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=expires_at,
        )
    )
    await session.commit()
    return raw_token


class RefreshTokenError(Exception):
    """
    Refresh token không hợp lệ vì bất kỳ lý do gì (không tồn tại, hết
    hạn, đã bị dùng ngoài grace period, đã bị thu hồi) - gộp chung 1
    loại lỗi, không phân biệt chi tiết lý do trong thông điệp trả về
    cho client, cùng nguyên tắc không rò rỉ thông tin qua kênh phụ đã
    áp dụng ở endpoint đăng nhập.
    """


async def rotate_refresh_token(session: AsyncSession, raw_token: str) -> tuple[int, str]:
    """
    Đổi 1 refresh token cũ lấy: (user_id, refresh token mới).

    Ba nhánh xử lý theo trạng thái của token được gửi lên:

    1. Chưa từng dùng, còn hạn, chưa bị thu hồi -> hợp lệ bình thường:
       đánh dấu đã dùng, phát token mới, ghi nhớ vào cache để trả lời
       nhất quán nếu có request khác đến sau hỏi lại đúng token này.

    2. Đã dùng, nhưng còn trong grace period, và cache còn nhớ token
       mới đã phát cho lần dùng đầu -> race condition vô hại (nhiều
       request hợp lệ cùng lúc): trả lại ĐÚNG token đã phát ở lần đầu.

    3. Đã dùng và (đã qua grace period, hoặc cache không còn nhớ - vd
       server vừa khởi động lại) -> dấu hiệu token bị đánh cắp: thu
       hồi toàn bộ refresh token khác của user này.
    """
    token_hash = hash_refresh_token(raw_token)

    result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    if stored is None:
        raise RefreshTokenError("Refresh token không tồn tại.")
    if stored.is_revoked:
        raise RefreshTokenError("Refresh token đã bị thu hồi.")
    if stored.expires_at < datetime.now(timezone.utc):
        raise RefreshTokenError("Refresh token đã hết hạn.")

    if stored.is_used:
        replacement_raw_token = _recall_replacement(token_hash)
        if replacement_raw_token is not None:
            return stored.user_id, replacement_raw_token

        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == stored.user_id, RefreshToken.is_revoked == False)  # noqa: E712
            .values(is_revoked=True)
        )
        await session.commit()
        raise RefreshTokenError("Refresh token đã được sử dụng - đã thu hồi toàn bộ phiên đăng nhập.")

    stored.is_used = True
    stored.used_at = datetime.now(timezone.utc)
    await session.commit()

    new_raw_token = await issue_refresh_token(session, stored.user_id)
    _remember_replacement(token_hash, new_raw_token)
    return stored.user_id, new_raw_token


async def revoke_all_refresh_tokens(session: AsyncSession, user_id: int) -> None:
    """Thu hồi toàn bộ refresh token còn hiệu lực của 1 user - dùng khi đăng xuất."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked == False)  # noqa: E712
        .values(is_revoked=True)
    )
    await session.commit()
