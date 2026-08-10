"""
Xác định câu hỏi của sinh viên thuộc KHÁI NIỆM nào - phục vụ Tutor
Agent (gia sư Socratic) biết sinh viên đang hỏi về chủ đề gì để tra
mức độ nắm vững (mastery) và điều chỉnh cách dẫn dắt cho phù hợp.

TỐI ƯU TỐC ĐỘ LÀ RÀNG BUỘC THIẾT KẾ CHÍNH (yêu cầu tường minh của
người dùng - hệ thống vốn đã chậm, không được thêm độ trễ):

- KHÔNG gọi LLM để phân loại (sẽ tốn thêm 1 round-trip ~1-2s).
- KHÔNG gọi API embedding riêng cho việc này: vector câu hỏi ĐÃ ĐƯỢC
  tính sẵn cho Hybrid Search, chỉ việc dùng lại; vector tên khái niệm
  đã tính sẵn lúc giảng viên TẠO khái niệm (xem app/learning/router.py).
- Việc còn lại chỉ là phép nhân vector trong bộ nhớ - với vài chục
  khái niệm mỗi lớp, thời gian tính bằng phần nghìn giây.

Đây chính là cách áp dụng lại nguyên tắc đã dùng cho Router Agent:
tái sử dụng embedding sẵn có khiến việc phân loại gần như MIỄN PHÍ cả
về tiền lẫn thời gian.
"""

import math
from dataclasses import dataclass

# Ngưỡng tương đồng tối thiểu để coi là "câu hỏi này thuộc khái niệm
# đó". Dưới ngưỡng => trả về None (không đoán bừa) - thà không biết
# khái niệm (gia sư dùng cách dẫn dắt mặc định) còn hơn gán nhầm khái
# niệm rồi đọc sai mức độ nắm vững của sinh viên, dẫn dắt sai hướng.
#
# Giá trị 0.35 chọn theo đặc điểm của cosine similarity trên
# text-embedding-3-small: 2 đoạn text CÙNG CHỦ ĐỀ nhưng khác độ dài
# (câu hỏi dài vs tên khái niệm ngắn 2-3 từ) thường rơi vào 0.35-0.6,
# hiếm khi lên cao như 2 đoạn văn cùng độ dài. Cần điều chỉnh lại nếu
# đo thực tế cho thấy gán nhầm/bỏ sót nhiều.
MIN_SIMILARITY = 0.35


@dataclass
class ConceptMatch:
    concept_id: int
    concept_name: str
    similarity: float


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def find_best_concept(
    query_vector: list[float], concepts: list[tuple[int, str, list[float] | None]]
) -> ConceptMatch | None:
    """
    Chọn khái niệm gần nghĩa nhất với câu hỏi.

    concepts: danh sách (concept_id, name, embedding) đã tải sẵn từ DB -
    hàm này KHÔNG tự truy vấn database (giữ hàm thuần, dễ kiểm thử, và
    quan trọng hơn: caller có thể tải danh sách này SONG SONG với các
    bước khác thay vì tuần tự).

    Trả về None nếu không khái niệm nào đủ gần (xem MIN_SIMILARITY) -
    khái niệm chưa có embedding (cột NULL, vd tạo trước khi có tính
    năng này) cũng bị bỏ qua an toàn.
    """
    best: ConceptMatch | None = None

    for concept_id, name, embedding in concepts:
        # KHÔNG dùng `if not embedding` ở đây: pgvector trả về numpy
        # array chứ không phải list Python, và numpy coi phép kiểm tra
        # "mảng này có rỗng/đúng không" trên mảng nhiều phần tử là NHẬP
        # NHẰNG rồi ném ValueError (đã gặp lỗi thật khi test). Phải hỏi
        # đúng câu cần hỏi: "có phải None không" và "có phần tử nào không".
        if embedding is None or len(embedding) == 0:
            continue
        score = _cosine_similarity(query_vector, list(embedding))
        if score >= MIN_SIMILARITY and (best is None or score > best.similarity):
            best = ConceptMatch(concept_id=concept_id, concept_name=name, similarity=score)

    return best
