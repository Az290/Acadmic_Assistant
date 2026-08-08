"""
Bước 1 của Ingestion Pipeline: đọc file PDF, lấy ra text SẠCH kèm thông
tin cấu trúc (trang nào, có phải heading không) - "nguyên liệu thô" cho
bước Chunking (chunker.py) xử lý tiếp.

Công cụ: PyMuPDF (tên thư viện: pymupdf, tên module cũ: fitz).

Vì sao chọn PyMuPDF thay vì Docling (đặc tả gốc đề xuất cho trường hợp
tổng quát): PyMuPDF cực nhanh (~0.1s/trang) và miễn phí, đủ tốt cho PDF
có "text-layer" sẵn (chữ có thể copy được, không phải ảnh scan) - đúng
loại tài liệu OpenStax/giáo trình số hoá thông thường ta dùng ở giai
đoạn này. Docling mạnh hơn với bảng biểu phức tạp/PDF scan nhưng nặng
hơn nhiều lần - để dành cho Phase 2 nếu sau này gặp tài liệu khó hơn
(đây chính là ý tưởng "route_parser thông minh" trong đặc tả gốc,
nhưng ta chưa cần bật nhánh Docling khi chưa có tài liệu nào cần nó).
"""

from dataclasses import dataclass

import pymupdf


@dataclass
class TextBlock:
    """
    Một khối văn bản trên 1 trang - đơn vị nhỏ nhất parser trả ra.

    is_heading: True nếu khối này có khả năng là tiêu đề chương/mục
    (dựa trên cỡ chữ lớn hơn hẳn văn bản thường) - chunker.py dùng cờ
    này để cắt heading-aware (ưu tiên cắt ngay trước 1 heading mới,
    thay vì cắt giữa chừng 1 đoạn văn).
    """

    page_number: int  # đánh số từ 1 (khớp cách người đọc thường nói "trang 5")
    text: str
    is_heading: bool
    font_size: float


def parse_pdf(file_path: str) -> list[TextBlock]:
    """
    Đọc toàn bộ PDF, trả về danh sách TextBlock theo đúng thứ tự xuất
    hiện trong tài liệu.

    Cách phát hiện heading: so cỡ chữ (font size) của từng khối văn bản
    với cỡ chữ PHỔ BIẾN NHẤT trong toàn tài liệu (coi là "cỡ chữ thân
    bài"). Khối nào có cỡ chữ lớn hơn rõ rệt (> 20%) được coi là heading.
    Đây là cách đơn giản, không cần AI, nhưng hoạt động tốt với hầu hết
    giáo trình/slide có phân cấp tiêu đề rõ ràng bằng cỡ chữ.
    """
    doc = pymupdf.open(file_path)

    # --- Bước phụ: xác định "cỡ chữ thân bài" bằng cách thống kê ---
    # Duyệt qua toàn bộ tài liệu trước 1 lượt, đếm xem cỡ chữ nào xuất
    # hiện NHIỀU KÝ TỰ NHẤT - đó chính là cỡ chữ của đoạn văn thường,
    # không phải heading (vì heading luôn ít chữ hơn thân bài rất nhiều).
    size_char_count: dict[float, int] = {}
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    size = round(span["size"], 1)
                    size_char_count[size] = size_char_count.get(size, 0) + len(span["text"])

    if not size_char_count:
        return []

    body_font_size = max(size_char_count, key=size_char_count.get)
    # Ngưỡng 1.4x (thay vì 1.2x ban đầu): thử nghiệm thật trên PDF
    # OpenStax cho thấy 1.2x quá thấp - vô tình bắt luôn cỡ chữ dùng
    # cho chú thích hình ảnh/caption (thường lớn hơn thân bài ~20%
    # nhưng KHÔNG phải heading). 1.4x tách rõ heading thật (thường lớn
    # hơn thân bài 40-300%) khỏi caption.
    heading_threshold = body_font_size * 1.4

    # --- Bước chính: duyệt lại, gom từng "block" PDF thành TextBlock ---
    blocks: list[TextBlock] = []
    for page_index, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue  # bỏ qua block không phải text (ảnh, hình vẽ...)

            block_text_parts = []
            max_size_in_block = 0.0
            for line in block["lines"]:
                for span in line["spans"]:
                    block_text_parts.append(span["text"])
                    max_size_in_block = max(max_size_in_block, span["size"])

            text = " ".join(block_text_parts).strip()
            if not text:
                continue

            blocks.append(
                TextBlock(
                    page_number=page_index + 1,
                    text=text,
                    is_heading=max_size_in_block >= heading_threshold,
                    font_size=round(max_size_in_block, 1),
                )
            )

    return blocks
