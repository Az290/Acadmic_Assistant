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
from app.retrieval.access_policy import chunk_access_sql

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

# Ngưỡng độ tương đồng TỐI THIỂU (cosine) để coi 1 chunk là "thật sự
# liên quan" tới câu hỏi. Dưới ngưỡng này, KHÔNG trả về kết quả nào -
# hệ thống thà nói "tài liệu chưa đề cập" còn hơn đưa cho AI đọc những
# đoạn văn không liên quan rồi để nó cố chắp vá thành câu trả lời.
#
# VÌ SAO CẦN (phát hiện qua đo thật): tìm kiếm vector LUÔN trả về N
# đoạn "gần nhất", kể cả khi tất cả đều không liên quan gì - hỏi "cách
# nấu phở bò" trong kho tài liệu Python vẫn ra đủ 8 kết quả. Không có
# ngưỡng thì hệ thống không bao giờ biết mình đang thiếu tài liệu.
#
# GIÁ TRỊ 0.30 chọn theo số liệu đo được với model text-embedding-3-large
# (xem app/ingestion/embedder.py): câu hỏi ĐÚNG chủ đề đạt 0.50-0.74,
# câu hỏi lạc đề chỉ 0.12-0.13. Ngưỡng 0.30 nằm giữa 2 nhóm, cách xa
# cả hai nên an toàn. LƯU Ý: ngưỡng này CHỈ đúng với model hiện tại -
# đổi model embedding thì phải đo và chỉnh lại (model cũ 3-small có 2
# nhóm chồng lấn nhau, không ngưỡng nào dùng được).
MIN_RELEVANCE_SIMILARITY = 0.30


@dataclass
class SearchResult:
    chunk_id: int
    document_id: int
    course_id: int  # môn học chứa chunk này - dùng để suy ra Conversation thuộc lớp nào (thống kê Dashboard giảng viên)
    content: str
    content_type: str
    page_number: int | None
    context_prefix: str | None
    score: float  # điểm RRF cuối cùng - CHỈ để xếp hạng, không có ý nghĩa tuyệt đối

    # Cosine similarity CAO NHẤT của cả lượt tìm kiếm này (giống nhau ở
    # mọi phần tử trong cùng 1 kết quả trả về) - KHÁC HẲN `score` ở trên:
    #
    # - score (RRF)          = tính từ THỨ HẠNG, giá trị ~0.016-0.033,
    #                          chỉ so sánh được với nhau, KHÔNG có ý
    #                          nghĩa tuyệt đối, KHÔNG được hiển thị cho
    #                          người dùng.
    # - retrieval_similarity = độ tương đồng ngữ nghĩa THẬT (0.0-1.0),
    #                          so sánh được qua các lượt hỏi khác nhau,
    #                          hiển thị được (nhãn "Độ khớp tài liệu").
    #
    # Mang theo ở đây thay vì đổi kiểu trả về của hybrid_search() thành
    # tuple: 4 nơi đang gọi hàm này, trong đó 2 nơi (quiz_generator,
    # retrieval/router) không cần tới giá trị này - thêm 1 field rẻ hơn
    # và ít rủi ro hơn việc sửa cả 4 chỗ gọi.
    retrieval_similarity: float


# ACL pre-filter DÙNG CHUNG cho cả 2 nhánh tìm kiếm - viết 1 lần, gọi ở
# cả 2 nơi, tránh 1 nhánh lỡ quên điều kiện khi sau này có ai sửa code.
#
# document.status = 'APPROVED' (Tác vụ #13, HITL) - PHÁT HIỆN QUA RÀ
# SOÁT: cột document.status đã tồn tại từ Tác vụ #4 (DRAFT/PROCESSING/
# PENDING_REVIEW/APPROVED/REJECTED/ARCHIVED) nhưng CHƯA TỪNG được lọc ở
# đây - nghĩa là tài liệu vừa upload xong (chưa ai duyệt) vẫn bị AI tìm
# thấy và dùng để trả lời ngay lập tức. Đúng nguyên tắc "chặn ở tầng dữ
# liệu" xuyên suốt dự án: chỉ tài liệu ĐÃ ĐƯỢC GIẢNG VIÊN DUYỆT mới lọt
# vào kết quả tìm kiếm, không phụ thuộc AI "tự biết" tài liệu nào đáng
# tin.
# Bộ lọc quyền đọc lấy từ app/retrieval/access_policy.py - ĐỊNH NGHĨA
# DUY NHẤT dùng chung với endpoint xem chi tiết đoạn trích dẫn
# (/v1/chunks/{id}). Trước đây file này giữ 2 bản sao thủ công (một cho
# tham số tên, một cho tham số vị trí) - mỗi lần đổi quy tắc quyền phải
# nhớ sửa cả 2, chỉ cần quên 1 chỗ là rò rỉ dữ liệu âm thầm.
_ACL_FILTER_SQL = chunk_access_sql()
_ACL_FILTER_SQL_POSITIONAL = chunk_access_sql(user_id_param="$2", is_admin_param="$4")


async def _vector_search(
    session: AsyncSession, query_vector: list[float], user_id: int, limit: int, is_admin: bool
) -> tuple[list[tuple[int, int]], float]:
    """
    Trả về ([(chunk_id, rank)], similarity_cao_nhat) xếp theo khoảng
    cách cosine tăng dần (gần nhất trước).

    similarity_cao_nhat dùng để quyết định "có tài liệu nào thật sự
    liên quan không" - xem MIN_RELEVANCE_SIMILARITY ở đầu file.

    Dùng exec_driver_sql() với tham số VỊ TRÍ ($1, $2...) thay vì
    session.execute(text(...), {...}) với tham số TÊN - lý do lịch
    sử: lúc điều tra độ trễ cao (đo được tới ~9s cho 1 lần gọi), ban
    đầu nghi ngờ SQLAlchemy compile chậm với tham số vector dạng chuỗi
    text ~30KB. Sau khi đo kỹ hơn (nhiều lần, nhiều session), phát
    hiện NGUYÊN NHÂN THẬT là Neon (Postgres serverless) có "cold
    start" - LẦN KẾT NỐI ĐẦU TIÊN trong 1 process luôn chậm (10-16s,
    dao động lớn) vì phải đánh thức compute instance sau thời gian
    idle; các lần sau (dùng lại connection pool) chỉ 1.5-2s. Đây
    KHÔNG PHẢI lỗi SQLAlchemy - kết luận ban đầu là kết luận sai do
    đo nhiễu bởi cold start, không phải bằng chứng thật.

    Giữ lại cách viết exec_driver_sql() này dù không giải quyết đúng
    nguyên nhân đã nghi ngờ - không gây hại, hoạt động đúng, và loại
    trừ khả năng compile chậm với tham số dài trong tương lai (dù
    chưa xác nhận chắc chắn đây có thật sự là rủi ro hay không). Với
    server chạy liên tục (không phải script test ngắn), cold start
    chỉ xảy ra ĐÚNG 1 LẦN lúc khởi động, không ảnh hưởng các request
    sau đó.
    """
    conn = await session.connection()
    result = await conn.exec_driver_sql(
        f"""
        SELECT id,
               ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS rank,
               1 - (embedding <=> $1::vector) AS similarity
        FROM chunk
        WHERE embedding IS NOT NULL AND {_ACL_FILTER_SQL_POSITIONAL}
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        (str(query_vector), user_id, limit, is_admin),
    )
    rows = list(result)
    ranked = [(row.id, row.rank) for row in rows]
    best_similarity = max((row.similarity for row in rows), default=0.0)
    return ranked, best_similarity


async def _fulltext_search(
    session: AsyncSession, query_text: str, user_id: int, limit: int, is_admin: bool
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
        {"query_text": query_text, "user_id": user_id, "limit": limit, "is_admin": is_admin},
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
    session: AsyncSession,
    query_text: str,
    user_id: int,
    top_k: int = TOP_K_FINAL,
    query_vector: list[float] | None = None,
    is_admin: bool = False,
    stats: dict | None = None,
) -> list[SearchResult]:
    """
    Hàm chính - nhận câu hỏi dạng text, trả về danh sách chunk liên
    quan nhất, đã lọc đúng quyền truy cập của user_id.

    query_vector: TUỲ CHỌN - nếu caller ĐÃ tính sẵn vector của chính
    query_text này cho mục đích khác (vd xác định khái niệm cho gia sư
    Socratic, xem app/learning/concept_matcher.py), truyền vào đây để
    KHÔNG phải gọi API embedding lần thứ 2 cho cùng 1 câu - tiết kiệm
    cả tiền lẫn ~1s độ trễ người dùng phải chờ.

    is_admin: ảnh hưởng quyền đọc đoạn INSTRUCTOR_ONLY (xem
    app/retrieval/access_policy.py). MẶC ĐỊNH False - chọn giá trị an
    toàn nhất làm mặc định: nơi gọi quên truyền thì người dùng bị coi
    như quyền thấp nhất, sai lầm dẫn tới "thấy ít hơn mức được phép"
    chứ không phải "thấy nhiều hơn".

    stats: THAM SỐ RA (out-param) TUỲ CHỌN - nếu caller truyền vào 1
    dict, hàm sẽ ghi khoá "best_similarity" (float) vào đó, LUÔN LUÔN,
    kể cả khi kết quả trả về là danh sách RỖNG do dưới ngưỡng.

    LÝ DO chọn out-param thay vì đổi kiểu trả về thành tuple: 4 nơi
    đang gọi hàm này, trong đó 2 nơi (quiz_generator, retrieval/router)
    hoàn toàn không quan tâm tới con số này - đổi chữ ký trả về buộc
    sửa cả 4 chỗ gọi. Còn dựa vào field SearchResult.
    retrieval_similarity thì KHÔNG đủ: đúng trường hợp quan trọng nhất
    (dưới ngưỡng -> trả []) lại không còn phần tử nào để mang giá trị
    đi. Hệ quả trước đây: DB ghi NULL, không phân biệt được "tra mà
    không thấy gì đủ gần" với "không hề tra cứu".
    """
    if query_vector is None:
        query_vector = embed_texts([query_text])[0]

    vector_ranked, best_similarity = await _vector_search(
        session, query_vector, user_id, TOP_K_PER_BRANCH, is_admin
    )

    # Ghi số đo RA NGOÀI NGAY tại đây - TRƯỚC mọi nhánh return sớm bên
    # dưới - để không lối thoát nào của hàm làm mất con số này.
    if stats is not None:
        stats["best_similarity"] = best_similarity

    # CHỐT SỚM: không đoạn tài liệu nào đủ liên quan tới câu hỏi -> trả
    # về RỖNG ngay, KHÔNG chạy tiếp nhánh tìm theo từ khoá.
    #
    # Đây là điều kiện làm cho hệ thống BIẾT KHI NÀO NÓ KHÔNG BIẾT: nếu
    # cứ trả về "N đoạn gần nhất" bất chấp độ liên quan (hành vi cũ),
    # AI sẽ nhận được toàn văn bản lạc đề rồi cố chắp vá thành câu trả
    # lời, còn giảng viên thì không bao giờ biết kho tài liệu đang
    # thiếu chủ đề nào (xem MIN_RELEVANCE_SIMILARITY ở đầu file).
    if best_similarity < MIN_RELEVANCE_SIMILARITY:
        return []

    fulltext_ranked = await _fulltext_search(session, query_text, user_id, TOP_K_PER_BRANCH, is_admin)

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
            SELECT id, document_id, course_id, content, content_type, page_number, context_prefix
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
            course_id=rows_by_id[chunk_id].course_id,
            content=rows_by_id[chunk_id].content,
            content_type=rows_by_id[chunk_id].content_type,
            page_number=rows_by_id[chunk_id].page_number,
            context_prefix=rows_by_id[chunk_id].context_prefix,
            score=scores_by_id[chunk_id],
            retrieval_similarity=best_similarity,
        )
        for chunk_id in top_chunk_ids
        if chunk_id in rows_by_id
    ]
