"""
Citation Verification (Tác vụ #10) - xác nhận TỰ ĐỘNG bằng thuật toán,
KHÔNG dựa vào AI "tự giác" khai đúng nguồn nó đã dùng (đúng nguyên tắc
xuyên suốt dự án: is_solution/visibility chặn ở SQL WHERE chứ không
chỉ dặn AI trong prompt - Citation cũng áp dụng cùng triết lý).

PHIÊN BẢN 2 - THAY THẾ cách tiếp cận n-gram ban đầu: bản đầu so khớp
n-gram giữa ANSWER (câu trả lời cuối, có thể đã DỊCH/DIỄN GIẢI sang
tiếng Việt) và CONTENT chunk gốc (thường tiếng Anh) - PHÁT HIỆN QUA
TEST THẬT: tài liệu tiếng Anh + câu trả lời tiếng Việt khiến n-gram
KHÔNG BAO GIỜ khớp dù nội dung hoàn toàn đúng, loại bỏ NHẦM citation
đúng ở gần như MỌI câu hỏi - không phải hiếm gặp mà là lỗi hệ thống.

CÁCH SỬA: bắt LLM tự trả về "quote" - đoạn trích NGUYÊN VĂN (không
dịch) từ chính chunk nó đã dùng (xem app/academic_agent/prompts.py::
CITATION_OUTPUT_CONTRACT) - việc so khớp giờ là quote (đã CÙNG NGÔN
NGỮ với chunk gốc, vì LLM được yêu cầu copy nguyên văn) với content
chunk, không còn vấn đề khác ngôn ngữ.

Vẫn còn 1 rủi ro cần biết: quote có thể bị LLM viết SAI 1-2 ký tự dù
có chủ ý copy nguyên văn (lỗi model, hiếm nhưng có thể) - dùng so khớp
LINH HOẠT (chuẩn hoá khoảng trắng/hoa-thường) thay vì so khớp tuyệt
đối từng ký tự, để không loại bỏ NHẦM citation đúng chỉ vì sai biệt
nhỏ không đáng kể.
"""

import re
import unicodedata


def _normalize(text: str) -> str:
    """
    Chuẩn hoá để so khớp LINH HOẠT: NFKC, lowercase, gộp khoảng trắng
    thừa, VÀ xoá khoảng trắng đứng NGAY TRƯỚC dấu câu - KHÔNG bỏ dấu
    tiếng Việt.

    PHÁT HIỆN QUA TEST THẬT: chunk gốc trích từ PDF thường có khoảng
    trắng THỪA quanh dấu câu do lỗi trích xuất PDF (vd: đã thấy chunk
    thật có `"part"  produces the string  "Apart" .` - khoảng trắng
    kép trước "produces" VÀ khoảng trắng trước dấu chấm cuối câu), còn
    quote do LLM tự gõ lại thường "sạch" hơn (khoảng trắng chuẩn). Chỉ
    gộp \\s+ thành 1 khoảng trắng KHÔNG đủ - vẫn còn 1 khoảng trắng dư
    ở vị trí "apart" . vs "apart". - phải xoá hẳn khoảng trắng ngay
    trước dấu câu mới khớp được.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,;:!?)\]}\"'])", r"\1", text)  # xoá khoảng trắng NGAY TRƯỚC dấu câu/ngoặc đóng
    return text.strip()


def verify_citations(citations: list[dict], chunk_contents: dict[int, str]) -> list[dict]:
    """
    Lọc lại danh sách citations LLM tự khai - chỉ giữ những citation có
    "quote" THẬT SỰ tìm thấy (dạng chuỗi con) trong content chunk gốc.

    citations: mỗi phần tử có {"chunk_id": int, "quote": str} (từ LLM),
    sẽ được BỔ SUNG thêm document_id/page_number ở agent.py sau khi lọc
    xong - hàm này chỉ lo việc XÁC MINH, không lo định dạng output cuối.

    chunk_contents: map chunk_id -> nội dung gốc (caller tự truyền vào,
    giữ hàm thuần, dễ test độc lập không cần DB).
    """
    verified: list[dict] = []
    for citation in citations:
        chunk_id = citation.get("chunk_id")
        quote = citation.get("quote", "")
        content = chunk_contents.get(chunk_id)

        if not quote or content is None:
            continue

        if _normalize(quote) in _normalize(content):
            verified.append(citation)
        # quote không khớp - LLM có thể đã bịa/dịch sai dù được dặn
        # không dịch - LOẠI BỎ, không hiển thị citation không đáng tin
        # cho sinh viên (thà thiếu còn hơn sai).

    return verified
