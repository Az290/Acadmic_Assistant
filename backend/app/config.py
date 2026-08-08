"""
Nơi tập trung MỌI cấu hình bí mật (connection string DB, API key...).

Nguyên tắc quan trọng: KHÔNG BAO GIỜ viết thẳng mật khẩu/API key vào code.
Thay vào đó, code chỉ đọc TÊN biến môi trường (environment variable) -
giá trị thật nằm trong file `.env` (không đưa lên Git, xem .gitignore).

Cách hoạt động: khi chạy server, thư viện `pydantic-settings` tự động
đọc file `.env` và "rót" giá trị vào các thuộc tính bên dưới. Nếu thiếu
biến bắt buộc, server sẽ báo lỗi ngay lúc khởi động (fail-fast) thay vì
chạy ngầm rồi lỗi khó hiểu lúc xử lý request.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Chuỗi kết nối tới Postgres (Neon).
    # Định dạng: postgresql+asyncpg://<user>:<password>@<host>/<dbname>
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/academic_assistant"

    # API key OpenAI - dùng cho cả LLM (agent) và embedding (tìm kiếm ngữ nghĩa)
    openai_api_key: str = ""

    # Bí mật dùng để ký JWT (Tác vụ #3 - Auth). Để trống ở tác vụ này,
    # sẽ bắt buộc điền khi làm Auth.
    jwt_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    """
    Trả về cấu hình, chỉ đọc file .env MỘT LẦN rồi lưu lại (cache).

    Vì sao cache: đọc file mỗi lần gọi sẽ chậm và không cần thiết -
    cấu hình không đổi trong lúc server đang chạy.
    """
    return Settings()
