"""
Kiểm tra chất lượng tài liệu vừa parse - phát hiện SỚM những vấn đề
khiến tài liệu "trông như đã xử lý xong" nhưng thực chất thiếu thông
tin quan trọng, để giảng viên biết trước khi duyệt.

Khác với ngưỡng CỨNG đã có trong app/ingestion/pipeline.py (chặn hẳn
nếu avg_chars_per_page < 50 - tài liệu gần như chắc chắn là bản scan,
không đọc được gì) - các cảnh báo ở đây là NGƯỠNG MỀM: tài liệu vẫn
được ingest bình thường (đã có đủ text để tìm kiếm), chỉ CẢNH BÁO
giảng viên có khả năng thiếu sót cần lưu ý.
"""

# Nếu > 30% số "trang có nội dung" chứa ảnh KHÔNG xử lý được (không có
# OCR/vision ở giai đoạn này - xem app/db/models.py::Document.image_count),
# cảnh báo tài liệu có thể thiếu thông tin quan trọng nằm trong hình
# (biểu đồ, công thức dạng ảnh, sơ đồ...).
IMAGE_RATIO_WARNING_THRESHOLD = 0.3

# Ngưỡng MỀM, thấp hơn ngưỡng CỨNG (50) trong pipeline.py nhưng vẫn
# đáng ngờ - tài liệu có chữ thật (không bị chặn hẳn) nhưng ít bất
# thường, có thể do PDF chứa nhiều bảng biểu/hình ảnh hơn văn bản
# thường, hoặc OCR một phần.
LOW_TEXT_DENSITY_WARNING_THRESHOLD = 150


def check_quality(*, avg_chars_per_page: float, image_count: int, total_pages: int) -> list[str]:
    warnings: list[str] = []

    if avg_chars_per_page < LOW_TEXT_DENSITY_WARNING_THRESHOLD:
        warnings.append(
            f"⚠️ Mật độ văn bản thấp bất thường (~{avg_chars_per_page:.0f} ký tự/trang) - "
            "tài liệu có thể chứa nhiều nội dung dạng ảnh/bảng biểu hơn văn bản thuần."
        )

    if total_pages > 0 and (image_count / total_pages) > IMAGE_RATIO_WARNING_THRESHOLD:
        warnings.append(
            f"⚠️ {image_count}/{total_pages} trang có ảnh/hình vẽ KHÔNG xử lý được nội dung "
            "(chưa hỗ trợ OCR/vision) - có thể thiếu thông tin quan trọng nằm trong hình."
        )

    return warnings
