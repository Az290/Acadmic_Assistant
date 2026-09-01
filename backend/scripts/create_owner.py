"""Tạo duy nhất tài khoản OWNER; mật khẩu tạm chỉ in ra một lần."""
import argparse
import asyncio
import secrets

from sqlalchemy import select

from app.auth.security import hash_password
from app.db.models import AppUser
from app.db.session import AsyncSessionLocal


async def create_owner(email: str, full_name: str) -> None:
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(AppUser).where(AppUser.email == email))).scalar_one_or_none()
        if existing is not None:
            raise SystemExit(f"Tài khoản {email} đã tồn tại (role={existing.role}); không tự ý đổi role hoặc mật khẩu.")
        current_owner = (await session.execute(select(AppUser).where(AppUser.role == "OWNER"))).scalar_one_or_none()
        if current_owner is not None:
            raise SystemExit(f"Hệ thống đã có OWNER: {current_owner.email}")

        temporary_password = secrets.token_urlsafe(18)
        session.add(AppUser(email=email, full_name=full_name, role="OWNER", password_hash=hash_password(temporary_password)))
        await session.commit()
        print(f"OWNER_EMAIL={email}")
        print(f"TEMPORARY_PASSWORD={temporary_password}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default="System Owner")
    args = parser.parse_args()
    asyncio.run(create_owner(args.email.strip().lower(), args.full_name.strip()))
