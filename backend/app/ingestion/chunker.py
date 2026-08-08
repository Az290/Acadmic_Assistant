"""
Cắt danh sách TextBlock (từ parser.py) thành các "chunk" - đơn vị văn
bản sẽ được embed và lưu vào bảng chunk để AI tìm kiếm sau này.

Chiến lược: HEADING-AWARE với FALLBACK RECURSIVE.
- Cắt ngay trước một heading mới khi có thể, để mỗi chunk không bị vắt
  ngang giữa 2 chủ đề khác nhau (giữ trọn vẹn ngữ nghĩa 1 mục).
- Nếu 1 mục quá dài (vượt kích thước tối đa), cắt tiếp theo kiểu
  "recursive" - chia nhỏ dần theo đoạn văn, có chồng lấn (overlap)
  giữa các chunk liền kề để không mất ngữ cảnh ở ranh giới cắt.

Kích thước: ~450 token/chunk, overlap 12% - nằm trong khoảng khuyến
nghị 400-512 token cho giáo trình PDF theo các benchmark chunking phổ biến.
"""

from dataclasses import dataclass, field

import tiktoken

from app.ingestion.parser import TextBlock

TARGET_CHUNK_TOKENS = 450
OVERLAP_RATIO = 0.12

# Dùng tokenizer của OpenAI để đếm token CHÍNH XÁC theo đúng cách model
# thật sẽ đếm - đếm bằng "số từ" hay "số ký tự" đều chỉ là ước lượng,
# dễ sai lệch khi tính chi phí/giới hạn ngữ cảnh cho model.
_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding.encode(text))


@dataclass
class ChunkDraft:
    """
    Một chunk "nháp" - đã cắt xong, sẵn sàng để Bước 3 (embedder.py)
    biến thành vector. Chưa có embedding, chưa có document_id (2 thứ
    đó được gắn vào ở pipeline.py, vì chunker.py không cần biết tài
    liệu này thuộc document nào - giữ module này thuần tuý, dễ test
    độc lập, đúng nguyên tắc mỗi file chỉ lo đúng 1 việc).
    """

    content: str
    page_number: int
    heading_context: str  # heading gần nhất trước chunk này, hỗ trợ định vị
    ord: int = 0  # thứ tự trong tài liệu - gán ở bước cuối cùng của hàm chunk_document


def chunk_document(blocks: list[TextBlock]) -> list[ChunkDraft]:
    """
    Hàm chính - nhận toàn bộ block của 1 tài liệu, trả về danh sách chunk.

    Thuật toán 2 giai đoạn:
    1. Gom các block liên tiếp thành từng "section" (mở đầu bằng 1
       heading, kết thúc trước heading tiếp theo).
    2. Với mỗi section: nếu đủ ngắn, giữ nguyên làm 1 chunk. Nếu quá
       dài, cắt tiếp theo kiểu recursive (chia nhỏ theo block, có
       overlap) để không vượt TARGET_CHUNK_TOKENS.
    """
    sections = _group_into_sections(blocks)

    drafts: list[ChunkDraft] = []
    for heading_text, section_blocks in sections:
        section_text = "\n".join(b.text for b in section_blocks)
        first_page = section_blocks[0].page_number

        if count_tokens(section_text) <= TARGET_CHUNK_TOKENS:
            # Section đủ ngắn - giữ nguyên khối, không cắt vụn thêm.
            # Điều này khớp nguyên tắc "bảng/công thức giữ nguyên khối,
            # không cắt" khi section đã tự nhiên ngắn gọn.
            drafts.append(
                ChunkDraft(content=section_text, page_number=first_page, heading_context=heading_text)
            )
        else:
            drafts.extend(
                _recursive_split(section_blocks, heading_context=heading_text)
            )

    for i, draft in enumerate(drafts):
        draft.ord = i

    return drafts


def _group_into_sections(
    blocks: list[TextBlock],
) -> list[tuple[str, list[TextBlock]]]:
    """
    Gom danh sách block phẳng thành các nhóm (section), mỗi nhóm bắt
    đầu ngay tại 1 heading. Nội dung TRƯỚC heading đầu tiên (vd: trang
    bìa) được gom vào 1 section "(mở đầu)" riêng.
    """
    sections: list[tuple[str, list[TextBlock]]] = []
    current_heading = "(mở đầu)"
    current_blocks: list[TextBlock] = []

    for block in blocks:
        if block.is_heading:
            if current_blocks:
                sections.append((current_heading, current_blocks))
            current_heading = block.text
            current_blocks = [block]
        else:
            current_blocks.append(block)

    if current_blocks:
        sections.append((current_heading, current_blocks))

    return sections


def _recursive_split(blocks: list[TextBlock], heading_context: str) -> list[ChunkDraft]:
    """
    Cắt 1 section quá dài thành nhiều chunk nhỏ hơn, gộp dần từng block
    cho tới khi gần chạm TARGET_CHUNK_TOKENS thì "chốt" thành 1 chunk,
    rồi lùi lại OVERLAP_RATIO số token để chunk tiếp theo có phần lặp
    lại - giữ ngữ cảnh liên tục qua ranh giới cắt (một câu bị cắt ngang
    ở cuối chunk này vẫn xuất hiện trọn vẹn ở đầu chunk kế tiếp).
    """
    overlap_tokens = int(TARGET_CHUNK_TOKENS * OVERLAP_RATIO)
    results: list[ChunkDraft] = []

    current_texts: list[str] = []
    current_tokens = 0
    current_first_page = blocks[0].page_number

    i = 0
    while i < len(blocks):
        block = blocks[i]
        block_tokens = count_tokens(block.text)

        if current_tokens + block_tokens > TARGET_CHUNK_TOKENS and current_texts:
            # Chốt chunk hiện tại
            results.append(
                ChunkDraft(
                    content="\n".join(current_texts),
                    page_number=current_first_page,
                    heading_context=heading_context,
                )
            )
            # Lùi lại để tạo overlap: giữ lại vài block cuối làm phần
            # mở đầu cho chunk tiếp theo, thay vì bắt đầu hoàn toàn mới.
            kept_texts: list[str] = []
            kept_tokens = 0
            for prev_text in reversed(current_texts):
                t = count_tokens(prev_text)
                if kept_tokens + t > overlap_tokens:
                    break
                kept_texts.insert(0, prev_text)
                kept_tokens += t

            current_texts = kept_texts
            current_tokens = kept_tokens
            current_first_page = block.page_number

        current_texts.append(block.text)
        current_tokens += block_tokens
        i += 1

    if current_texts:
        results.append(
            ChunkDraft(
                content="\n".join(current_texts),
                page_number=current_first_page,
                heading_context=heading_context,
            )
        )

    return results
