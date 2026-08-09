"""
Cấu hình log dạng JSON có cấu trúc (structured logging), thay cho log
dạng chữ tự do (`print(...)` hoặc log mặc định của uvicorn).

Vì sao cần: khi có lỗi xảy ra trên production, câu hỏi đầu tiên luôn là
"request nào gây ra lỗi này, vào lúc nào, của user nào". Log dạng chữ
tự do không tra cứu được câu hỏi đó một cách đáng tin cậy (phải đoán
theo timestamp gần đúng). Log JSON có `request_id` xuyên suốt 1 request
cho phép lọc chính xác toàn bộ log liên quan tới đúng request đó, kể cả
khi nhiều request khác đang chạy xen kẽ cùng lúc (bình thường với
server bất đồng bộ như FastAPI).

Lựa chọn có chủ đích: dùng thẳng module `logging` chuẩn của Python +
1 formatter JSON tự viết (vài chục dòng), KHÔNG dùng dịch vụ ngoài như
Datadog/Sentry/Grafana Cloud - ở quy mô hiện tại (chưa có traffic thật),
thêm 1 dịch vụ trả phí chỉ để có dashboard đẹp là chi phí không tương
xứng lợi ích. Log JSON in ra console/file vẫn đọc được bằng mắt thường
lẫn công cụ dòng lệnh (`jq`), và có thể trỏ thẳng vào dịch vụ ngoài sau
này (hầu hết đều nhận input JSON qua stdout) mà không cần đổi lại cách
ghi log ở đây.
"""

import json
import logging
import sys
from contextvars import ContextVar

# ContextVar (khác biến toàn cục thường): mỗi request bất đồng bộ chạy
# trong "ngữ cảnh" (context) riêng của nó dù cùng chia sẻ 1 process -
# ContextVar đảm bảo request A không vô tình đọc/ghi đè request_id của
# request B đang chạy xen kẽ cùng lúc.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """
    Gọi 1 lần lúc khởi động app (main.py) - thay thế cấu hình log mặc
    định bằng handler ghi JSON ra stdout.

    Vì sao phải override CẢ logger "uvicorn"/"uvicorn.access", không
    chỉ root logger: uvicorn tự cấu hình 2 logger con này bằng handler
    riêng của nó (log dạng chữ tự do "INFO: ...") NGAY KHI SERVER KHỞI
    ĐỘNG - việc này xảy ra SAU khi configure_logging() chạy (vì
    configure_logging() chạy lúc import module app.main, còn uvicorn tự
    setup log của nó khi start() được gọi) nên ghi đè mất cấu hình JSON
    đã đặt cho root logger. Phải tắt propagate=False + gắn handler JSON
    trực tiếp vào từng logger con này để chúng không tự in ra theo
    format riêng của uvicorn nữa.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False
