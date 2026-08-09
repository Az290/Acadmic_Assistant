"""
Tạo tài khoản ADMIN đầu tiên - chạy TAY, MỘT LẦN, lúc mới deploy hệ
thống lên một database còn trống.

Vì sao không có endpoint API công khai làm việc này: nếu có, bất kỳ ai
gọi được API cũng có thể tự phong ADMIN cho chính mình - đây phải là
thao tác chỉ người có quyền truy cập trực tiếp vào server/database mới
làm được (giống lệnh `createsuperuser` của Django, hay việc thêm dòng
đầu tiên vào 1 bảng phân quyền bằng tay). Sau khi có ADMIN đầu tiên, họ
dùng chính tài khoản này để tạo tài khoản giảng viên qua API
POST /v1/auth/admin/create-instructor (xem app/auth/router.py).

Cách chạy (từ thư mục backend/, đã kích hoạt virtualenv):
    python scripts/create_admin.py --email admin@truong.edu.vn --full-name "Quan tri vien" --password "mat-khau-manh"

Nếu bỏ --password, script tự sinh 1 mật khẩu ngẫu nhiên và in ra màn
hình - dùng cách này khi chạy trên server thật để tránh mật khẩu bị
lưu lại trong lịch sử dòng lệnh (shell history).
"""

import argparse
import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.auth.security import hash_password
from app.db.models import AppUser
from app.db.session import AsyncSessionLocal


async def create_admin(email: str, full_name: str, password: str) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(AppUser).where(AppUser.email == email))
        if existing.scalar_one_or_none() is not None:
            print(f"Lỗi: email '{email}' đã tồn tại trong hệ thống - không tạo lại.")
            return

        admin = AppUser(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role="ADMIN",
        )
        session.add(admin)
        await session.commit()
        print(f"Đã tạo ADMIN: {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo tài khoản ADMIN đầu tiên cho hệ thống.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--password", default=None, help="Bỏ trống để tự sinh mật khẩu ngẫu nhiên.")
    args = parser.parse_args()

    password = args.password or secrets.token_urlsafe(12)
    if args.password is None:
        print(f"Mật khẩu tự sinh (lưu lại ngay, không hiển thị lại lần nữa): {password}")

    asyncio.run(create_admin(args.email, args.full_name, password))


if __name__ == "__main__":
    main()
