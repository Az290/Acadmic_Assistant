"""
Tìm kiếm đoạn văn bản liên quan nhất tới 1 câu hỏi - "trái tim" của
RAG (Retrieval-Augmented Generation): trước khi AI trả lời, phải tìm
đúng những đoạn tài liệu liên quan để "cho AI đọc" kèm theo câu hỏi.

Chiến lược: HYBRID SEARCH - kết hợp 2 cách tìm khác nhau, mỗi cách
mạnh ở một mặt mà cách kia yếu:

- VECTOR SEARCH (ngữ nghĩa): so sánh vector embedding của câu hỏi với
  vector của từng chunk (khoảng cách cosine). Tìm được đoạn văn LIÊN
  QUAN VỀ Ý NGHĨA dù không dùng chung từ ("cách lặp qua danh sách" vẫn
  tìm ra đoạn nói về "vòng lặp for"). Điểm yếu: có thể bỏ lỡ khi câu
  hỏi chứa 1 THUẬT NGỮ/MÃ ĐỊNH DANH cụ thể (tên hàm, từ khoá đúng
  chính tả) mà vector không ưu tiên khớp chính xác.

- FULL-TEXT SEARCH kiểu từ khoá (Postgres tsvector + ts_rank): tìm
  theo TỪ KHOÁ CHÍNH XÁC xuất hiện trong văn bản. Mạnh khi câu hỏi có
  thuật ngữ/tên hàm cụ thể ("round() hoạt động thế nào") - vector
  search có thể xếp hạng thấp những đoạn này vì "ngữ nghĩa tổng thể"
  của chúng không nổi bật, dù chứa đúng từ khoá cần tìm.

  Lưu ý thuật ngữ: đây KHÔNG PHẢI thuật toán BM25 thật (dù cùng họ
  "lexical/keyword ranking"). ts_rank tính điểm dựa trên vị trí và mật
  độ từ khớp trong văn bản, không có tham số chuẩn hoá theo độ dài
  trung bình toàn corpus hay hệ số bão hoà tần suất từ như công thức
  BM25 chuẩn (Okapi BM25). Dùng ts_rank vì có sẵn trong Postgres,
  không cần cài thêm hạ tầng (Elasticsearch/OpenSearch) - đủ dùng ở
  quy mô hiện tại, nhưng gọi đúng tên để không gây hiểu lầm khi đọc
  code sau này.

- RRF (Reciprocal Rank Fusion): gộp 2 danh sách xếp hạng (không phải
  gộp điểm số thô - điểm cosine và điểm ts_rank có thang đo hoàn toàn
  khác nhau, cộng trực tiếp sẽ vô nghĩa) thành 1 danh sách cuối, dựa
  trên THỨ HẠNG của mỗi kết quả trong từng danh sách con. Công thức
  đơn giản, không cần huấn luyện, đã được dùng rộng rãi trong các hệ
  RAG production thật. Gộp theo chunk_id - 1 chunk xuất hiện ở CẢ 2
  danh sách sẽ được cộng dồn điểm từ cả 2 nhánh.

ACL (kiểm soát quyền truy cập) LUÔN LÀ ĐIỀU KIỆN SQL nhúng trong CHÍNH
câu truy vấn của MỖI nhánh (không lọc sau khi có kết quả, và không lọc
sau khi RRF đã chạy) - đúng nguyên tắc "ACL pre-filter" đã áp dụng
xuyên suốt dự án: suy ra course được phép từ user_id qua bảng
enrollment (KHÔNG tin course_id nếu client tự gửi - ở đây endpoint
thậm chí không nhận tham số course_id nào), và luôn loại
is_solution=TRUE (chunk chứa đáp án bài tập) khỏi mọi kết quả tìm
kiếm - dù prompt AI có bị "bẻ khoá" thế nào, đáp án cũng không bao giờ
lọt vào vì nó bị chặn ngay ở tầng truy vấn dữ liệu, không dựa vào AI
"tự biết đừng dùng".

Embedding của câu hỏi (query) dùng CHUNG hàm embed_texts() và CHUNG
model (EMBEDDING_MODEL trong app/ingestion/embedder.py) với embedding
của chunk lúc ingest - bắt buộc phải cùng 1 model, vì vector từ 2 model
khác nhau (dù cùng số chiều 1536) không nằm trong cùng không gian toạ
độ, so sánh cosine giữa chúng sẽ cho kết quả vô nghĩa.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.embedder import embed_texts

# Số kết quả lấy ra từ MỖI nhánh (vector, full-text) trước khi gộp - lấy
# nhiều hơn số kết quả cuối cùng cần trả (TOP_K_FINAL) để RRF có đủ
# "nguyên liệu" xếp hạng lại, tránh bỏ sót 1 kết quả xếp hạng vừa phải
# ở cả 2 nhánh nhưng lại không lọt top-K quá hẹp của từng nhánh riêng.
TOP_K_PER_BRANCH = 20
TOP_K_FINAL = 8

# Hằng số k trong công thức RRF: score = sum(1 / (k + rank)). Giá trị
# 60 là con số phổ biến trong các nghiên cứu/hệ thống RRF gốc - làm
# "giảm xóc" ảnh hưởng của thứ hạng quá cao (rank=1) để không lấn át
# hoàn toàn kết quả tốt ở nhánh còn lại.
RRF_K = 60


@dataclass
class SearchResult:
    chunk_id: int
    document_id: int
    content: str
    content_type: str
    page_number: int | None
    context_prefix: str | None
    score: float  # điểm RRF cuối cùng - CHỈ để xếp hạng, không có ý nghĩa tuyệt đối


# ACL pre-filter DÙNG CHUNG cho cả 2 nhánh tìm kiếm - viết 1 lần, gọi ở
# cả 2 nơi, tránh 1 nhánh lỡ quên điều kiện khi sau này có ai sửa code.
_ACL_FILTER_SQL = """
    chunk.course_id IN (
        SELECT course_id FROM enrollment WHERE user_id = :user_id
    )
    AND chunk.is_solution = FALSE
"""


async def _vector_search(
    session: AsyncSession, query_vector: list[float], user_id: int, limit: int
) -> list[tuple[int, int]]:
    """Trả về [(chunk_id, rank)] xếp theo khoảng cách cosine tăng dần (gần nhất trước)."""
    result = await session.execute(
        text(
            f"""
            SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:query_vector AS vector)) AS rank
            FROM chunk
            WHERE embedding IS NOT NULL AND {_ACL_FILTER_SQL}
            ORDER BY embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
            """
        ),
        {"query_vector": str(query_vector), "user_id": user_id, "limit": limit},
    )
    return [(row.id, row.rank) for row in result]


async def _fulltext_search(
    session: AsyncSession, query_text: str, user_id: int, limit: int
) -> list[tuple[int, int]]:
    """
    Trả về [(chunk_id, rank)] xếp theo ts_rank giảm dần (khớp từ khoá
    nhất trước). Đây là full-text search kiểu từ khoá của Postgres
    (ts_rank), KHÔNG PHẢI thuật toán BM25 thật - xem giải thích chi
    tiết ở docstring đầu file.
    """
    result = await session.execute(
        text(
            f"""
            SELECT id, ROW_NUMBER() OVER (
                ORDER BY ts_rank(content_tsv, websearch_to_tsquery('simple', :query_text)) DESC
            ) AS rank
            FROM chunk
            WHERE content_tsv @@ websearch_to_tsquery('simple', :query_text) AND {_ACL_FILTER_SQL}
            ORDER BY ts_rank(content_tsv, websearch_to_tsquery('simple', :query_text)) DESC
            LIMIT :limit
            """
        ),
        {"query_text": query_text, "user_id": user_id, "limit": limit},
    )
    return [(row.id, row.rank) for row in result]


def _reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[int, int]]], k: int = RRF_K
) -> list[tuple[int, float]]:
    """
    Gộp nhiều danh sách [(id, rank)] thành 1 danh sách [(id, rrf_score)]
    xếp theo điểm RRF giảm dần - id xuất hiện ở NHIỀU danh sách con,
    hoặc xếp hạng CAO trong 1 danh sách, sẽ có điểm cuối cao hơn.
    """
    scores: dict[int, float] = {}
    for ranked_list in ranked_lists:
        for chunk_id, rank in ranked_list:
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


async def hybrid_search(
    session: AsyncSession, query_text: str, user_id: int, top_k: int = TOP_K_FINAL
) -> list[SearchResult]:
    """
    Hàm chính - nhận câu hỏi dạng text, trả về danh sách chunk liên
    quan nhất, đã lọc đúng quyền truy cập của user_id.
    """
    query_vector = embed_texts([query_text])[0]

    vector_ranked = await _vector_search(session, query_vector, user_id, TOP_K_PER_BRANCH)
    fulltext_ranked = await _fulltext_search(session, query_text, user_id, TOP_K_PER_BRANCH)

    # RRF hoạt động đúng kể cả khi 1 trong 2 danh sách rỗng (vd câu hỏi
    # thuần khái niệm không khớp từ khoá nào, hoặc chuỗi ký tự lạ
    # không có hàng xóm ngữ nghĩa nào đủ gần) - dict.get() trong hàm
    # gộp không đòi hỏi cả 2 danh sách phải có cùng phần tử.
    fused = _reciprocal_rank_fusion([vector_ranked, fulltext_ranked])
    top_chunk_ids = [chunk_id for chunk_id, _ in fused[:top_k]]

    if not top_chunk_ids:
        return []

    # Lấy đầy đủ nội dung cho đúng top_k chunk đã chọn - tách riêng
    # bước "xếp hạng" (chỉ cần id) và bước "lấy nội dung" (cần đủ cột)
    # để 2 câu SQL ở trên gọn, không phải SELECT * khi chỉ đang xếp hạng.
    result = await session.execute(
        text(
            """
            SELECT id, document_id, content, content_type, page_number, context_prefix
            FROM chunk
            WHERE id = ANY(:chunk_ids)
            """
        ),
        {"chunk_ids": top_chunk_ids},
    )
    rows_by_id = {row.id: row for row in result}
    scores_by_id = dict(fused)

    return [
        SearchResult(
            chunk_id=chunk_id,
            document_id=rows_by_id[chunk_id].document_id,
            content=rows_by_id[chunk_id].content,
            content_type=rows_by_id[chunk_id].content_type,
            page_number=rows_by_id[chunk_id].page_number,
            context_prefix=rows_by_id[chunk_id].context_prefix,
            score=scores_by_id[chunk_id],
        )
        for chunk_id in top_chunk_ids
        if chunk_id in rows_by_id
    ]
