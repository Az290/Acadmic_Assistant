"""
Middleware gắn 1 request_id (UUID) DUY NHẤT cho mỗi request HTTP - dùng
cùng với app/logging_config.py để mọi dòng log phát sinh trong lúc xử
lý 1 request đều mang chung request_id đó.

Middleware trong FastAPI/Starlette: 1 lớp bọc quanh MỌI request, chạy
trước khi vào endpoint và sau khi endpoint trả lời xong - cùng khuôn
mẫu với CORSMiddleware đã dùng ở main.py, ở đây tự viết vì đây là logic
đặc thù của dự án (không phải middleware có sẵn của thư viện ngoài).
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.logging_config import request_id_ctx

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Nếu client (vd: hạ tầng gateway phía trước) đã tự gắn sẵn 1
        # request_id, giữ nguyên id đó thay vì tạo mới - cho phép truy
        # vết xuyên suốt nhiều tầng hạ tầng bằng 1 id thống nhất. Nếu
        # không có, tự sinh UUID mới.
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        current_id = incoming_id or uuid.uuid4().hex

        token = request_id_ctx.set(current_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)

        response.headers[REQUEST_ID_HEADER] = current_id
        return response
