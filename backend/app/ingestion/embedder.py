"""
Biến mỗi chunk (đoạn văn bản) thành 1 vector 1536 chiều bằng OpenAI
"text-embedding-3-small", để lưu vào cột `embedding` của bảng chunk.

Điểm quan trọng về CHI PHÍ: gọi API theo BATCH (gộp nhiều chunk vào 1
lần gọi) thay vì gọi lẻ từng chunk một. OpenAI cho phép gửi tối đa
2048 đoạn văn bản trong 1 lần gọi embedding - gộp lại giảm đáng kể số
lượt gọi HTTP (mỗi lượt gọi network có "phí cố định" về độ trễ, dù nội
dung ít hay nhiều), dù tổng token tính phí không đổi.

EMBEDDING_VERSION: ghi lại đúng tên model đã dùng vào cột
embedding_version của mỗi chunk - để sau này nếu đổi model embedding
khác, hệ thống biết chunk nào cần re-index lại, không phải áp dụng mù
quáng cho toàn bộ dữ liệu cũ.
"""

from openai import OpenAI

from app.config import get_settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_VERSION = "openai-text-embedding-3-small-v1"

# Giới hạn an toàn cho mỗi lượt gọi batch - thấp hơn mức tối đa OpenAI
# cho phép (2048), để tránh 1 request quá lớn bị timeout hoặc vượt
# giới hạn token tổng của API.
BATCH_SIZE = 100

_settings = get_settings()
_client = OpenAI(api_key=_settings.openai_api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Nhận danh sách đoạn văn bản, trả về danh sách vector tương ứng
    (cùng thứ tự, cùng độ dài) - tự động chia thành nhiều batch nếu
    danh sách đầu vào dài hơn BATCH_SIZE.
    """
    all_embeddings: list[list[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        response = _client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        # OpenAI trả kết quả ĐÚNG THEO THỨ TỰ đầu vào - an toàn để zip lại.
        all_embeddings.extend(item.embedding for item in response.data)

    return all_embeddings
