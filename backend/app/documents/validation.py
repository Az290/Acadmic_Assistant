"""
Kiểm tra file upload TRƯỚC KHI đưa vào Ingestion Pipeline.

Vì sao cần bước riêng này: nếu chỉ tin vào phần đuôi file (".pdf") và
không giới hạn dung lượng, một file quá khổ hoặc 1 file đổi đuôi giả
mạo (thực chất là .exe/.zip) có thể làm treo server hoặc tốn tài
nguyên vô ích trước khi parser kịp báo lỗi.
"""

from fastapi import HTTPException, UploadFile, status

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB - đủ cho giáo trình vài trăm trang có hình ảnh

# "Magic bytes": vài byte đầu tiên của file cho biết ĐÚNG LOẠI file thật
# sự là gì, không phụ thuộc vào tên/đuôi file (dễ giả mạo). Mọi file PDF
# hợp lệ luôn bắt đầu bằng chuỗi "%PDF-" - đây là quy ước chuẩn của định
# dạng PDF, không phải điều gì đặc thù của dự án này.
PDF_MAGIC_BYTES = b"%PDF-"


def validate_upload_filename(filename: str | None) -> None:
    if not filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chỉ hỗ trợ file PDF.",
        )


def validate_file_size(file_bytes: bytes) -> None:
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        limit_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File quá lớn ({size_mb:.1f}MB) - giới hạn tối đa {limit_mb:.0f}MB.",
        )
    if len(file_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File rỗng.")


def validate_pdf_magic_bytes(file_bytes: bytes) -> None:
    """
    Kiểm tra file THẬT SỰ là PDF, không chỉ tin đuôi ".pdf" trong tên.

    Đây là lớp phòng thủ thực dụng: chặn được trường hợp ai đó đổi tên
    "malware.exe" thành "baigiang.pdf" rồi upload - nếu không có bước
    này, file sẽ được lưu và đưa thẳng vào PyMuPDF, thất bại với lỗi
    khó hiểu (hoặc tệ hơn, gây hành vi không lường trước được).
    """
    if not file_bytes.startswith(PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nội dung file không phải PDF hợp lệ (kiểm tra thất bại ở magic bytes).",
        )
