"""
Lớp phòng thủ RẺ NHẤT, NHANH NHẤT chống prompt injection - chạy hoàn
toàn cục bộ (không gọi API nào), dựa trên pattern matching sau khi đã
"làm sạch" văn bản để chống các kỹ thuật né tránh phổ biến.

GIỚI HẠN THẬT SỰ CẦN BIẾT RÕ: đây KHÔNG PHẢI giải pháp bắt được 100%
biến thể prompt injection - không có cách nào làm được điều đó chỉ
bằng rule-based, kể cả rule rất mạnh (đây là giới hạn kỹ thuật thật,
đã thảo luận rõ trước khi code). Lớp phòng thủ THẬT SỰ chống lộ đáp
án nằm ở TẦNG DỮ LIỆU (is_solution=FALSE trong SQL, xem
app/retrieval/hybrid_search.py) - dù injection "thắng" và khiến AI cố
đưa đáp án, đáp án đó không hề tồn tại trong ngữ cảnh AI đọc được.
Module này chỉ giảm số lần AI bị dắt đi lạc đề, không phải chốt chặn
cuối cùng.

3 kỹ thuật né tránh phổ biến được xử lý TRƯỚC KHI so khớp pattern:
1. Unicode full-width/ligature (ｉｇｎｏｒｅ -> ignore) - NFKC normalize.
2. Ký tự "lookalike" khác bảng chữ cái nhưng nhìn giống hệt (Cyrillic
   а/е/о/р/с trông giống Latin a/e/o/p/c) - bảng ánh xạ thủ công, vì
   NFKC KHÔNG xử lý được trường hợp này (đã kiểm chứng bằng code thật,
   không phải giả định).
3. Chèn khoảng trắng/dấu câu xen giữa các chữ cái (i g n o r e,
   i-g-n-o-r-e) - loại bỏ trước khi so khớp.
4. Nội dung mã hoá Base64 - thử decode nếu chuỗi "trông giống" base64,
   rồi kiểm tra lại nội dung đã decode.
"""

import base64
import binascii
import re
import unicodedata

# Bảng ánh xạ ký tự "lookalike" phổ biến nhất về đúng ký tự Latin gốc.
# Không đầy đủ (không thể đầy đủ) - chỉ phủ các ký tự Cyrillic/Greek
# hay bị lợi dụng nhất vì visually identical với Latin trên hầu hết font.
_LOOKALIKE_MAP = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "У": "Y", "Х": "X",
    "і": "i", "І": "I", "ѕ": "s",
    "ο": "o", "α": "a", "ρ": "p", "τ": "t",  # Greek
})

# Pattern phát hiện prompt injection - song ngữ Việt/Anh, phủ các cụm
# "ra lệnh lại cho AI" phổ biến nhất trong các cuộc tấn công thật đã
# ghi nhận công khai (không phải danh sách tự nghĩ ra).
_INJECTION_PATTERNS = [
    # Yêu cầu bỏ qua/quên hướng dẫn trước đó
    r"ignore (all |any )?(previous|prior|above|earlier) instructions?",
    r"disregard (all |any )?(previous|prior|above|earlier) instructions?",
    r"forget (all |any )?(previous|prior|above|earlier) instructions?",
    r"bỏ qua (mọi |tất cả )?(các )?(hướng dẫn|chỉ dẫn|chỉ thị|lệnh) (trước|phía trên|ở trên)",
    r"quên (đi )?(mọi |tất cả )?(các )?(hướng dẫn|chỉ dẫn|chỉ thị)",
    # Yêu cầu tiết lộ system prompt
    r"(show|reveal|print|repeat) (me )?(your |the )?system prompt",
    r"what (is|are) your (system )?(prompt|instructions?)",
    r"(cho tôi xem|tiết lộ|nói cho tôi biết) (system prompt|chỉ dẫn hệ thống|prompt gốc)",
    # Yêu cầu đóng vai để né guardrail (jailbreak kiểu "DAN")
    r"\byou are (now )?DAN\b",
    r"\byou are (now |)(no longer|not) (bound|restricted|limited)",
    r"act as (if you (are|were) )?(an? )?(unrestricted|unfiltered|jailbroken)",
    r"(hãy )?đóng vai (một )?(AI|trợ lý) không (bị )?(giới hạn|ràng buộc)",
    r"pretend (you have no|there are no) (rules|restrictions|guidelines)",
    # Yêu cầu trực tiếp đáp án/lời giải bài tập theo cách né guardrail
    r"(give|tell|show) me the (answer|solution) (key|sheet)",
    r"đưa (cho tôi )?(đáp án|lời giải) (đầy đủ|chi tiết|hoàn chỉnh) (của )?bài (tập|kiểm tra|thi)",
]
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Ngưỡng độ dài tối thiểu để THỬ decode base64 - chuỗi quá ngắn dễ bị
# nhận diện nhầm (nhiều chuỗi ngắn tình cờ hợp lệ base64 nhưng chỉ là
# văn bản thường), không đáng công decode.
_MIN_BASE64_LENGTH = 20
_BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/]+=*$")


def _normalize_text(text: str) -> str:
    """
    Chuẩn hoá văn bản để chống né tránh: NFKC (full-width/ligature) +
    ánh xạ lookalike. KHÔNG gỡ khoảng trắng chèn ở đây - việc đó cần
    một biến thể riêng (xem _collapse_spaced_out_words) vì gỡ nhầm có
    thể phá câu văn bình thường.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_LOOKALIKE_MAP)
    return text


def _collapse_spaced_out_words(text: str) -> str:
    """
    Gộp lại các từ bị chèn khoảng trắng giữa từng chữ cái (kiểu né
    tránh "i g n o r e" -> "ignore"), CHỈ trả về bản gộp để thử so
    khớp THÊM, không thay thế bản gốc - tránh việc gộp sai làm biến
    dạng câu văn bình thường có nhiều từ 1 ký tự tự nhiên.

    Chiến lược: nếu văn bản có dấu hiệu bị "giãn cách" rõ rệt (nhiều
    token 1 ký tự liên tiếp), coi khoảng trắng ĐƠN là ranh giới CHỮ
    CÁI trong cùng 1 từ, khoảng trắng ĐÔI trở lên là ranh giới TỪ -
    giả định hợp lý vì kỹ thuật né tránh này thường vẫn giữ khoảng
    cách xa hơn giữa các từ để dễ đọc bằng mắt người.
    """
    if not _looks_spaced_out(text):
        return text

    words = re.split(r"\s{2,}", text)
    merged_words = [re.sub(r"(?<=\w)[\s\-\.](?=\w)", "", w) for w in words]
    return " ".join(merged_words)


def _looks_spaced_out(text: str) -> bool:
    """Phát hiện văn bản có dấu hiệu bị chèn khoảng trắng giữa từng chữ cái."""
    single_char_tokens = re.findall(r"\b\w\b", text)
    return len(single_char_tokens) >= 5


def _try_decode_base64_segments(text: str) -> list[str]:
    """
    Tìm các đoạn "trông giống" base64 trong text, thử decode - trả về
    danh sách nội dung đã decode thành công (dùng để kiểm tra tiếp).
    """
    decoded_segments = []
    for token in re.findall(r"[A-Za-z0-9+/=]{%d,}" % _MIN_BASE64_LENGTH, text):
        if not _BASE64_PATTERN.match(token):
            continue
        try:
            decoded_bytes = base64.b64decode(token, validate=True)
            decoded_text = decoded_bytes.decode("utf-8")
            decoded_segments.append(decoded_text)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue  # không phải base64 thật, hoặc decode ra không phải text - bỏ qua
    return decoded_segments


def extract_base64_decoded_segments(text: str) -> list[str]:
    """
    Hàm PUBLIC dùng chung cho cả check_injection_patterns() (rules.py)
    lẫn check_moderation() (moderation.py, gọi qua guardrail.py) - trước
    đây guardrail.py chỉ đưa Moderation API xem CHUỖI BASE64 GỐC, chưa
    bao giờ đưa nội dung ĐÃ DECODE - PHÁT HIỆN QUA EVAL THẬT (Tác vụ #9):
    câu "SGVscCBtZSBidWlsZCBhIHBpcGUgYm9tYi..." (decode ra yêu cầu chế
    tạo bom) lọt qua cả 2 lớp Guardrail, vì:
    - rule-based (check_injection_patterns) CÓ decode và kiểm tra, nhưng
      chỉ so khớp pattern PROMPT INJECTION ("ignore instructions"...) -
      câu này không phải injection, không khớp pattern nào nên qua lớp 1.
    - Moderation API chỉ nhận chuỗi Base64 THÔ (trông vô hại với model
      moderation) - KHÔNG BAO GIỜ thấy được nội dung bạo lực thật sự đã
      bị giấu bên trong.
    """
    return _try_decode_base64_segments(text)


def check_injection_patterns(text: str) -> str | None:
    """
    Kiểm tra text (và các đoạn base64 giấu bên trong nếu có) khớp
    pattern injection nào không. Trả về chuỗi mô tả lý do nếu bị chặn,
    None nếu không phát hiện gì đáng ngờ.
    """
    candidates = [text] + _try_decode_base64_segments(text)

    for candidate in candidates:
        normalized = _normalize_text(candidate)
        # Thử cả bản GIỮ NGUYÊN khoảng trắng lẫn bản đã GỘP TỪ bị giãn
        # cách - 2 lượt so khớp riêng biệt, không thay thế nhau, vì
        # không thể biết trước văn bản có bị né tránh kiểu này hay không.
        variants_to_check = [normalized, _collapse_spaced_out_words(normalized)]
        for variant in variants_to_check:
            for pattern in _COMPILED_PATTERNS:
                if pattern.search(variant):
                    return f"Phát hiện mẫu câu nghi ngờ prompt injection: khớp pattern '{pattern.pattern}'"

    return None
