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

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Chuỗi kết nối tới Postgres (Neon).
    # Định dạng: postgresql+asyncpg://<user>:<password>@<host>/<dbname>
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/academic_assistant"

    # API key OpenAI - dùng cho cả LLM (agent) và embedding (tìm kiếm ngữ nghĩa)
    openai_api_key: str = ""

    # Model rieng cho Evidence Planner de co the A/B test ma khong doi model
    # sinh cau tra loi. Tat bang NOVA_EVIDENCE_PLANNER_ENABLED=false de rollback.
    nova_evidence_planner_enabled: bool = True
    nova_evidence_planner_model: str = "gpt-4o-mini"
    nova_evidence_planner_timeout_seconds: float = 12.0

    # Bounded Retrieval Phase 3. Tat multi-query de quay ve hybrid_search cu.
    nova_multi_query_enabled: bool = False
    nova_query_generator_model: str = "gpt-4o-mini"
    nova_query_generator_timeout_seconds: float = 10.0
    nova_max_search_queries: int = 3
    nova_retrieval_candidate_limit: int = 20
    nova_reranker_enabled: bool = False
    nova_reranker_model: str = "gpt-4o-mini"
    nova_reranker_timeout_seconds: float = 12.0

    # Phase 4: Composer tach rieng khoi retrieval/planner. Tat de rollback ve
    # lenh chat.completions legacy trong agent.py.
    nova_response_composer_enabled: bool = True

    # Bí mật dùng để ký JWT. PHẢI điền giá trị ngẫu nhiên thật trong
    # .env trước khi chạy - sinh bằng lệnh:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    #
    # KHÔNG có giá trị mặc định an toàn cho biến này - _validate_not_blank
    # bên dưới CHỦ ĐỘNG chặn server khởi động nếu nó bị bỏ trống. Một
    # chuỗi rỗng "trông giống" giá trị hợp lệ về mặt kiểu dữ liệu
    # (vẫn là str) nhưng jwt.encode(payload, "", ...) vẫn ký được token
    # bình thường - nghĩa là "bí mật" ký token lúc đó là công khai, ai
    # cũng tự ký được JWT giả mạo bất kỳ role nào. Việc "để dành trống,
    # tự set sau" là điều KHÔNG được phép xảy ra âm thầm.
    jwt_secret: str = ""

    # JWT dùng thuật toán nào để ký - HS256 là chuẩn phổ biến, đủ an
    # toàn cho quy mô 1 backend service (không cần thuật toán bất đối
    # xứng phức tạp hơn như RS256, vốn dùng khi nhiều service khác
    # nhau cùng cần xác minh token mà không được biết bí mật ký).
    jwt_algorithm: str = "HS256"

    # ACCESS token (JWT) hết hạn sau bao nhiêu phút - đây là token dùng
    # cho MỌI request thường ngày. Access token KHÔNG tra được DB để
    # biết có bị thu hồi hay chưa (đó là bản chất JWT - tự chứa, không
    # cần tra DB mới nhanh) - nên phải sống NGẮN, để nếu bị lộ thì
    # thiệt hại giới hạn trong 30 phút. Phiên đăng nhập được "nối dài"
    # qua REFRESH token (xem bên dưới), không phải bằng cách kéo dài
    # access token.
    jwt_expire_minutes: int = 30

    # REFRESH token sống dài hơn nhiều - đây là "vé" dùng để xin cấp
    # lại access token mới mà không cần gõ lại mật khẩu. Khác access
    # token, refresh token có bản ghi THẬT trong bảng refresh_token ->
    # có thể thu hồi giữa chừng (đánh dấu is_revoked), đây là lý do
    # chính để tách 2 loại token thay vì chỉ dùng 1 JWT sống dài duy nhất.
    refresh_token_expire_days: int = 7

    # Danh sách domain ĐƯỢC PHÉP gọi API này từ trình duyệt (CORS).
    # Phân tách bằng dấu phẩy trong .env, ví dụ:
    #   CORS_ALLOWED_ORIGINS=http://localhost:3000,https://academic-assistant.vercel.app
    #
    # Mặc định chỉ có localhost:3000 (nơi Next.js chạy lúc code trên
    # máy) - KHÔNG dùng "*" (cho phép mọi domain), vì làm vậy đồng nghĩa
    # bất kỳ trang web nào trên Internet cũng gọi được API kèm cookie
    # đăng nhập của user nếu họ đang mở tab đó, dẫn tới rủi ro rò rỉ
    # dữ liệu qua cross-origin request.
    cors_allowed_origins: str = "http://localhost:3000"

    # Thuộc tính SameSite của cookie đăng nhập - QUYẾT ĐỊNH TRỰC TIẾP
    # việc đăng nhập có hoạt động trên production hay không:
    #
    # - "lax" (mặc định, dùng khi chạy trên máy): trình duyệt CHỈ gửi
    #   cookie khi request xuất phát từ CÙNG site. Lúc dev, frontend
    #   (localhost:3000) và backend (localhost:8001) tuy khác cổng
    #   nhưng vẫn được coi là cùng site -> hoạt động bình thường.
    #
    # - "none" (BẮT BUỘC khi frontend và backend nằm ở 2 domain khác
    #   nhau, vd Vercel + Fly.io): nếu để "lax" trong tình huống này,
    #   trình duyệt sẽ ÂM THẦM không gửi cookie -> mọi request đều bị
    #   coi như chưa đăng nhập, dù login vừa thành công.
    #
    # ĐÁNH ĐỔI khi dùng "none": cookie được gửi kèm cả request từ site
    # khác, mở ra khả năng bị tấn công CSRF. Lớp phòng thủ còn lại là
    # CORS whitelist (chỉ domain trong danh sách mới gọi được API bằng
    # JavaScript) + việc API chỉ nhận JSON (buộc trình duyệt phải gửi
    # preflight, vốn bị CORS chặn). An toàn hơn nữa là đặt frontend và
    # backend CÙNG domain (Vercel proxy /api/* về backend) rồi giữ
    # "lax" - xem hướng dẫn triển khai trong DEPLOY.md.
    cookie_samesite: str = "lax"

    # Cookie chỉ gửi qua HTTPS. Luôn để True: trình duyệt có NGOẠI LỆ
    # cho localhost (vẫn chấp nhận cookie secure trên http://localhost)
    # nên không cần tắt khi chạy máy cá nhân.
    cookie_secure: bool = True

    # Voice transcription settings
    # Whisper API pricing: $0.006 per minute
    whisper_cost_per_minute: float = 0.006

    # Maximum audio file size in MB
    max_audio_size_mb: int = 25

    # Shared secret cho webhook connector o Phase 6. Production nen dat rieng;
    # neu chua co, mock foundation tam dung JWT_SECRET de khong pha env hien tai.
    connector_webhook_secret: str | None = None
    discord_connector_enabled: bool = False
    discord_bot_token: str | None = None
    discord_bot_user_id: str | None = None
    discord_internal_api_base: str = "http://127.0.0.1:8001"
    zalo_connector_enabled: bool = False
    zalo_gmf_enabled: bool = False
    zalo_oa_access_token: str | None = None
    zalo_oa_id: str | None = None
    zalo_internal_api_base: str = "http://127.0.0.1:8001"
    # Secret cua endpoint trung gian do minh kiem soat (reverse proxy/webhook app),
    # khong nham thay the co che xac minh cua Zalo neu OA duoc cap contract rieng.
    zalo_callback_secret: str | None = None
    connector_event_retention_days: int = 7
    connector_processing_timeout_seconds: int = 300
    nova_rollout_percent: int = 100
    nova_rollback_dead_jobs_threshold: int = 5
    nova_rollback_p95_latency_ms: int = 20000
    public_web_url: str = "http://localhost:3000"

    @field_validator("nova_rollout_percent")
    @classmethod
    def _validate_rollout_percent(cls, value: int) -> int:
        if not 0 <= value <= 100:
            raise ValueError("NOVA_ROLLOUT_PERCENT phai nam trong khoang 0..100")
        return value

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @field_validator("jwt_secret", "openai_api_key")
    @classmethod
    def _validate_not_blank(cls, value: str, info) -> str:
        """
        Chặn server khởi động nếu 1 bí mật bắt buộc bị bỏ trống trong
        .env/biến môi trường - "fail fast" thật sự, thay vì chỉ ghi
        chú bằng lời rồi hy vọng không ai quên set.

        Đặc biệt quan trọng với jwt_secret: khác openai_api_key (thiếu
        thì chỉ hỏng tính năng ingestion, báo lỗi rõ ràng lúc gọi API),
        jwt_secret rỗng khiến TOÀN BỘ hệ thống xác thực mất tác dụng
        bảo vệ một cách ÂM THẦM - server vẫn chạy, mọi request vẫn có
        vẻ hoạt động bình thường, chỉ khác là ai cũng tự ký được JWT
        giả mạo. Lỗi kiểu "âm thầm vẫn chạy nhưng mất an toàn" nguy
        hiểm hơn nhiều so với server không khởi động được.
        """
        if not value.strip():
            raise ValueError(
                f"Biến môi trường '{info.field_name.upper()}' đang trống - "
                "bắt buộc phải điền giá trị thật trong .env trước khi chạy server."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """
    Trả về cấu hình, chỉ đọc file .env MỘT LẦN rồi lưu lại (cache).

    Vì sao cache: đọc file mỗi lần gọi sẽ chậm và không cần thiết -
    cấu hình không đổi trong lúc server đang chạy.
    """
    return Settings()
