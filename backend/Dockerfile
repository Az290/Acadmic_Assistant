# Ảnh nền "slim": có sẵn Python, bỏ bớt công cụ không cần thiết -
# nhỏ hơn ảnh đầy đủ vài trăm MB, khởi động nhanh hơn, ít lỗ hổng bảo
# mật tiềm ẩn hơn (ít phần mềm cài sẵn = ít thứ cần vá).
# Ghim ĐÚNG phiên bản 3.11 khớp với môi trường đang phát triển - tránh
# việc bản mới hơn trên máy chủ làm lộ ra lỗi chưa từng gặp lúc code.
FROM python:3.11-slim

# Không sinh file .pyc (thừa trong container, chỉ làm ảnh nặng thêm)
# và không đệm log (để log hiện ra NGAY, không bị giữ lại trong bộ nhớ
# đệm - quan trọng khi xem log lỗi trên máy chủ theo thời gian thực).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Cài thư viện TRƯỚC khi chép mã nguồn - đây là mẹo tận dụng cache của
# Docker: mỗi lần sửa code (rất thường xuyên) sẽ không phải cài lại
# toàn bộ thư viện (rất chậm), vì lớp cài đặt phía trên không đổi.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cổng mặc định Fly.io chờ ứng dụng lắng nghe (khớp internal_port
# trong fly.toml).
EXPOSE 8080

# --host 0.0.0.0: bắt buộc trong container - nếu để mặc định
# (127.0.0.1), ứng dụng chỉ nhận kết nối từ BÊN TRONG container, mọi
# request từ ngoài vào đều bị từ chối.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
