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

    # Bí mật dùng để ký JWT (Tác vụ #3 - Auth). PHẢI điền giá trị ngẫu
    # nhiên thật trong .env trước khi chạy - sinh bằng lệnh:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret: str = ""

    # JWT dùng thuật toán nào để ký - HS256 là chuẩn phổ biến, đủ an
    # toàn cho quy mô 1 backend service (không cần thuật toán bất đối
    # xứng phức tạp hơn như RS256, vốn dùng khi nhiều service khác
    # nhau cùng cần xác minh token mà không được biết bí mật ký).
    jwt_algorithm: str = "HS256"

    # Token hết hạn sau bao nhiêu phút - hết hạn thì phải đăng nhập lại.
    # 7 ngày = 10080 phút: đủ dài để không làm phiền user đăng nhập lại
    # liên tục, nhưng vẫn có giới hạn thay vì "sống mãi mãi".
    jwt_expire_minutes: int = 10080


@lru_cache
def get_settings() -> Settings:
    """
    Trả về cấu hình, chỉ đọc file .env MỘT LẦN rồi lưu lại (cache).

    Vì sao cache: đọc file mỗi lần gọi sẽ chậm và không cần thiết -
    cấu hình không đổi trong lúc server đang chạy.
    """
    return Settings()
