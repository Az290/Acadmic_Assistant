"""
Rate limiting cơ bản theo SỐ LƯỢT REQUEST.

QUAN TRỌNG - ranh giới của module này: đây CHỈ là hàng rào chống
spam/DoS đơn giản (giới hạn "bao nhiêu LƯỢT gọi/phút"), KHÔNG PHẢI
giới hạn chi phí LLM theo TOKEN. Giới hạn token chỉ có ý nghĩa khi đã
có endpoint gọi LLM thật cho chat (Academic Agent) - hiện tại, endpoint
"nặng" nhất là Ingestion (gọi OpenAI embedding), nhưng đó là hành động
của giáo viên (ít, có kiểm soát qua ACL), không phải học sinh gọi tự
do - nên rate-limit theo request là đủ ở giai đoạn này. Giới hạn
token/chi phí thật sự sẽ làm khi có Agent chat.

Công cụ: slowapi (thư viện nhỏ, đếm ngay trong process, không cần
Redis/service ngoài) - đủ dùng ở quy mô vài chục user test. Nếu sau
này chạy nhiều instance backend cùng lúc (scale ngang), sẽ cần chuyển
sang đếm tập trung qua Redis để các instance "biết" nhau.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# get_remote_address: đếm rate-limit theo ĐỊA CHỈ IP người gọi - đơn
# giản, không cần biết user đã đăng nhập hay chưa (hoạt động được cả
# cho /login, nơi user CHƯA có JWT để định danh theo cách khác).
#
# config_filename="" (KHÔNG để mặc định None): nếu để None, slowapi tự
# ý đọc file ".env" ở thư mục hiện tại bằng encoding hệ thống (không
# phải UTF-8) - vì file .env của dự án có tiếng Việt (trong comment),
# việc này gây UnicodeDecodeError ngay lúc khởi động. Dự án đã dùng
# pydantic-settings (app/config.py) để đọc .env đúng cách UTF-8 rồi,
# không cần slowapi đọc lại theo cách riêng của nó.
limiter = Limiter(key_func=get_remote_address, config_filename="")

# Giới hạn mặc định cho MỌI endpoint chưa khai báo riêng - chống spam
# cơ bản. 60 lần/phút = trung bình 1 request/giây, đủ rộng rãi cho
# thao tác bình thường (bấm nút, load trang) nhưng chặn được vòng lặp
# gọi API tự động.
DEFAULT_RATE_LIMIT = "60/minute"

# Giới hạn CHẶT HƠN riêng cho endpoint đăng nhập - đây là nơi cụ thể
# cần chống brute-force (dò mật khẩu hàng loạt). 5 lần/phút vẫn đủ cho
# người dùng thật gõ sai vài lần, nhưng chặn được máy tự động thử hàng
# trăm mật khẩu trong thời gian ngắn.
LOGIN_RATE_LIMIT = "5/minute"
