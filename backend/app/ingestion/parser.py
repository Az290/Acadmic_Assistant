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

import re
from dataclasses import dataclass

import pymupdf

# PHÁT HIỆN QUA TEST THẬT (ingest "Open Data Structures" - Pat Morin,
# PDF sinh từ LaTeX): PyMuPDF trích ra byte NUL (\x00) xen giữa văn bản
# bình thường ở 3/711 chunk, làm asyncpg ném CharacterNotInRepertoireError
# lúc INSERT ("invalid byte sequence for encoding UTF8: 0x00") - Postgres
# CẤM TUYỆT ĐỐI byte NUL trong cột text/varchar (giới hạn ở tầng lưu trữ
# C-string, không liên quan gì tới UTF-8 hợp lệ hay không).
#
# Truy vết tận gốc: không phải lỗi ligature "ffi" như nghi ngờ ban đầu -
# đọc trực tiếp span PyMuPDF cho thấy \x00 (và \x01, \x10-\x13 ở chỗ
# khác) đến từ font "Kp--M-Ex-Regular" (Computer Modern Math Extension) -
# đây là font LaTeX dùng để vẽ CÁC MẢNH DẤU NGOẶC KÉO DÃN (vd: ngoặc lớn
# bao quanh tổ hợp chập nhị thức "n choose k" \binom{n}{k}) - những glyph
# này thuần tuý trang trí, KHÔNG có Unicode codepoint thật tương ứng, nên
# PyMuPDF map chúng vào các mã điều khiển C0 thấp (0x00-0x1F) khi không
# tìm được ánh xạ hợp lệ. Đây KHÔNG phải lỗi riêng của file này - vấn đề
# đã biết trong hệ sinh thái PyMuPDF/PDF parsing với font toán học/font
# nhúng lỗi nói chung (PDF LaTeX cũ, PDF scan OCR cũng có nguy cơ tương
# tự) - nên xử lý ở TẦNG PIPELINE, ngay tại nguồn trích xuất, thay vì vá
# riêng cho 1 file.
#
# Chỉ loại bỏ ĐÚNG các mã điều khiển không in được (giữ lại tab/newline/CR
# vì đó là khoảng trắng hợp lệ) - KHÔNG xoá cả đoạn/câu chứa nó, tránh mất
# nội dung học thuật thật xung quanh (chunker.py vẫn ghép câu bình thường,
# chỉ riêng glyph rác biến mất).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _strip_control_chars(text: str) -> str:
    """
    Dọn control character rác (byte NUL và các mã điều khiển C0/C1 khác)
    ra khỏi text thô PyMuPDF trả về - làm NGAY tại đây (điểm dữ liệu bẩn
    xuất hiện lần đầu) thay vì để lọt xuống chunker.py hay pipeline.py,
    vì mọi TextBlock từ giờ về sau (kể cả bảng) đều đi qua đúng 1 cổng
    này - chặn sớm nhất, áp dụng cho MỌI file PDF sau này chứ không chỉ
    riêng file gây lỗi lần này.
    """
    return _CONTROL_CHAR_RE.sub("", text)


@dataclass
class ParseResult:
    """
    Kết quả đầy đủ của việc parse 1 file PDF - không chỉ danh sách
    block văn bản, mà kèm cả thống kê về phần KHÔNG xử lý được (ảnh).

    image_count: tổng số ảnh/hình vẽ trong toàn tài liệu - KHÔNG trích
    xuất hay mô tả nội dung ảnh (không làm OCR/vision ở giai đoạn này,
    xem lý do trong docstring parse_pdf() bên dưới), chỉ ĐẾM để hệ
    thống biết "tài liệu này có N phần chưa xử lý được" - dữ liệu này
    dùng để quyết định sau này có đáng đầu tư thêm OCR/vision hay
    không, thay vì làm mù quáng ngay từ đầu.
    """

    blocks: list["TextBlock"]
    image_count: int


@dataclass
class TextBlock:
    """
    Một khối văn bản trên 1 trang - đơn vị nhỏ nhất parser trả ra.

    is_heading: True nếu khối này có khả năng là tiêu đề chương/mục
    (dựa trên cỡ chữ lớn hơn hẳn văn bản thường) - chunker.py dùng cờ
    này để cắt heading-aware (ưu tiên cắt ngay trước 1 heading mới,
    thay vì cắt giữa chừng 1 đoạn văn).

    content_type: "TEXT" (mặc định) hoặc "TABLE". Một block TABLE có
    `text` ở dạng markdown table (hàng phân cách bằng "\\n", cột phân
    cách bằng " | ") thay vì văn bản chạy dài - giữ được cấu trúc
    hàng-cột thay vì để PyMuPDF đọc lộn xộn theo thứ tự toạ độ.
    """

    page_number: int  # đánh số từ 1 (khớp cách người đọc thường nói "trang 5")
    text: str
    is_heading: bool
    font_size: float
    content_type: str = "TEXT"


def parse_pdf(file_path: str) -> ParseResult:
    """
    Đọc toàn bộ PDF, trả về danh sách TextBlock theo đúng thứ tự xuất
    hiện trong tài liệu, kèm số lượng ảnh đã gặp (không xử lý nội dung).

    Cách phát hiện heading: so cỡ chữ (font size) của từng khối văn bản
    với cỡ chữ PHỔ BIẾN NHẤT trong toàn tài liệu (coi là "cỡ chữ thân
    bài"). Khối nào có cỡ chữ lớn hơn rõ rệt (> 20%) được coi là heading.
    Đây là cách đơn giản, không cần AI, nhưng hoạt động tốt với hầu hết
    giáo trình/slide có phân cấp tiêu đề rõ ràng bằng cỡ chữ.

    Vì sao KHÔNG làm OCR/mô tả ảnh bằng AI ở đây: tốn chi phí (gọi
    thêm 1 API vision cho mỗi ảnh) và độ phức tạp không tương xứng khi
    chưa biết thực tế có bao nhiêu tài liệu THẬT SỰ cần tới nó. Đếm số
    ảnh trước, dùng con số đó để đưa ra quyết định đầu tư đúng chỗ sau.
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
        return ParseResult(blocks=[], image_count=0)

    body_font_size = max(size_char_count, key=size_char_count.get)
    # Ngưỡng 1.4x (thay vì 1.2x ban đầu): thử nghiệm thật trên PDF
    # OpenStax cho thấy 1.2x quá thấp - vô tình bắt luôn cỡ chữ dùng
    # cho chú thích hình ảnh/caption (thường lớn hơn thân bài ~20%
    # nhưng KHÔNG phải heading). 1.4x tách rõ heading thật (thường lớn
    # hơn thân bài 40-300%) khỏi caption.
    heading_threshold = body_font_size * 1.4

    # --- Bước chính: duyệt lại, gom từng "block" PDF thành TextBlock ---
    blocks: list[TextBlock] = []
    image_count = 0
    for page_index, page in enumerate(doc):
        # Phát hiện vùng có bảng TRƯỚC khi duyệt text block thường của
        # trang này - dùng find_tables() có sẵn trong PyMuPDF (không
        # cần thư viện ngoài nào khác). Đây là cách rẻ, không hoàn hảo
        # với bảng phức tạp (ô gộp, không có đường kẻ rõ ràng) nhưng đủ
        # dùng cho bảng có cấu trúc rõ ràng (kẻ ô hoặc căn cột đều đặn)
        # thường gặp trong giáo trình.
        table_finder = page.find_tables()
        table_bboxes = [pymupdf.Rect(t.bbox) for t in table_finder.tables]

        for table in table_finder.tables:
            rows = table.extract()
            # Bỏ qua bảng "rỗng" (find_tables() thỉnh thoảng phát hiện
            # nhầm 1 khung kẻ trang trí không chứa dữ liệu thật).
            if not rows or not any(any(cell for cell in row) for row in rows):
                continue
            markdown_rows = [
                " | ".join(_strip_control_chars(cell or "") for cell in row) for row in rows
            ]
            blocks.append(
                TextBlock(
                    page_number=page_index + 1,
                    text="\n".join(markdown_rows),
                    is_heading=False,
                    font_size=body_font_size,
                    content_type="TABLE",
                )
            )

        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                # block không phải text - trong PyMuPDF, "type=1" là
                # ảnh raster (không phải hình vẽ vector như đường kẻ
                # bảng, những cái đó không tạo ra block riêng ở đây).
                # KHÔNG trích xuất nội dung, chỉ đếm để biết tài liệu
                # có bao nhiêu phần chưa xử lý được (xem ParseResult).
                if block.get("type") == 1:
                    image_count += 1
                continue

            block_rect = pymupdf.Rect(block["bbox"])
            # Bỏ qua text block nằm TRONG vùng đã xử lý thành bảng ở
            # trên - tránh nội dung bảng bị đọc/lưu 2 LẦN (một lần dạng
            # markdown table có cấu trúc, một lần dạng text chạy dài
            # lộn xộn từ chính những ô đó).
            if any(block_rect in bbox or bbox.intersects(block_rect) for bbox in table_bboxes):
                continue

            block_text_parts = []
            max_size_in_block = 0.0
            for line in block["lines"]:
                for span in line["spans"]:
                    # Dọn control char rác ngay tại đây - đây là điểm
                    # text thô của PyMuPDF lần đầu trở thành str Python,
                    # trước khi ghép câu/đoạn hay đưa vào chunker.
                    block_text_parts.append(_strip_control_chars(span["text"]))
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

    return ParseResult(blocks=blocks, image_count=image_count)
