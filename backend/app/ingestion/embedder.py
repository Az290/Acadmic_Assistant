"""
Biến mỗi chunk (đoạn văn bản) thành 1 vector 1536 chiều bằng OpenAI
"text-embedding-3-large", để lưu vào cột `embedding` của bảng chunk.

VÌ SAO ĐỔI TỪ "3-small" SANG "3-large" (đo bằng dữ liệu thật, không
phải chọn theo cảm tính): với nội dung/câu hỏi TIẾNG VIỆT, model
"3-small" KHÔNG phân biệt được câu hỏi có liên quan tài liệu hay
không - đo thực tế cho thấy câu hỏi hoàn toàn lạc đề ("cách nấu phở
bò") vẫn đạt độ tương đồng 0.32, trong khi câu hỏi ĐÚNG chủ đề chỉ đạt
0.40-0.46. Hai nhóm chồng lấn nhau nên không tồn tại ngưỡng nào tách
được chúng.

Cùng phép đo đó với "3-large": câu lạc đề tụt xuống 0.12-0.13, câu
đúng chủ đề giữ 0.50-0.74 - tách bạch rõ ràng, khoảng cách an toàn
~0.37. Đây là điều kiện BẮT BUỘC để hệ thống biết khi nào mình "không
có tài liệu để trả lời" thay vì bịa dựa trên đoạn văn không liên quan.

dimensions=1536: model "3-large" mặc định trả 3072 chiều, nhưng nó hỗ
trợ giảm chiều (kỹ thuật Matryoshka - các chiều đầu đã mang phần lớn
thông tin). Chọn 1536 vì 2 lý do THỰC TẾ: (1) pgvector chỉ tạo được
index HNSW cho vector tối đa 2000 chiều, 3072 sẽ không có index và tìm
kiếm sẽ chậm dần khi dữ liệu lớn; (2) giữ nguyên cấu trúc bảng hiện
có, không phải sửa schema. Đã đo: chất lượng ở 1536 chiều KHÔNG kém
3072 chiều (thậm chí nhỉnh hơn chút ở bộ câu hỏi thử).

Điểm quan trọng về CHI PHÍ: gọi API theo BATCH (gộp nhiều chunk vào 1
lần gọi) thay vì gọi lẻ từng chunk một. OpenAI cho phép gửi tối đa
2048 đoạn văn bản trong 1 lần gọi embedding - gộp lại giảm đáng kể số
lượt gọi HTTP (mỗi lượt gọi network có "phí cố định" về độ trễ, dù nội
dung ít hay nhiều), dù tổng token tính phí không đổi. Model "3-large"
đắt hơn "3-small" (~6.5 lần) nhưng embedding chỉ chạy 1 lần lúc ingest
tài liệu, không phải mỗi câu hỏi - tổng chi phí vẫn rất nhỏ so với
lợi ích chất lượng.

EMBEDDING_VERSION: ghi lại đúng tên model đã dùng vào cột
embedding_version của mỗi chunk - để sau này nếu đổi model embedding
khác, hệ thống biết chunk nào cần re-index lại, không phải áp dụng mù
quáng cho toàn bộ dữ liệu cũ.
"""

from openai import OpenAI

from app.config import get_settings

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_VERSION = "openai-text-embedding-3-large-1536-v1"

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
        response = _client.embeddings.create(
            model=EMBEDDING_MODEL, input=batch, dimensions=EMBEDDING_DIMENSIONS
        )
        # OpenAI trả kết quả ĐÚNG THEO THỨ TỰ đầu vào - an toàn để zip lại.
        all_embeddings.extend(item.embedding for item in response.data)

    return all_embeddings
