"""
Đo chất lượng Retrieval bằng bộ câu hỏi cố định - chạy TRƯỚC và SAU mỗi
thay đổi để biết thay đổi đó có thật sự cải thiện hay không.

VÌ SAO CẦN: trước đây mọi kết luận về retrieval đều dựa trên cột
message.retrieval_similarity, nhưng cột đó chỉ có dữ liệu ở 37/120 dòng
(rỗng khi search trả về 0 kết quả) - so sánh trước/sau bằng nó là so
sánh trên mẫu thiên lệch. Script này đo TRỰC TIẾP qua hybrid_search()
với user_id thật nên luôn đi qua ACL, không phụ thuộc dữ liệu lịch sử.

BẮT BUỘC đi qua hybrid_search(user_id=...) chứ KHÔNG query thẳng bảng
chunk - đã có lần kết luận sai vì bỏ qua ACL (xem PROJECT_CONTEXT, mục
bác bỏ giả thuyết "giáo trình trùng").

Chạy:
    .venv/Scripts/python.exe -X utf8 scripts/retrieval_baseline.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import AsyncSessionLocal
from app.retrieval.hybrid_search import MIN_RELEVANCE_SIMILARITY, hybrid_search

# user 25 = sv.sinhvien1@test.edu.vn, enroll course 1 (có giáo trình Python)
TEST_USER_ID = 25

# ON = nội dung CÓ trong giáo trình -> đáng lẽ phải tìm được
# OFF = chắc chắn KHÔNG có -> đáng lẽ phải trả rỗng
CASES = [
    ("What is a Python list?", "ON"),
    ("String concatenation in Python", "ON"),
    ("How does recursion work?", "ON"),
    ("Python variables and types", "ON"),
    ("How to use a for loop in Python?", "ON"),
    ("Cau truc du lieu list dict set trong Python la gi?", "ON"),
    ("Hàm đệ quy hoạt động như thế nào?", "ON"),
    ("Ham de quy hoat dong nhu the nao?", "ON"),
    ("Cach cai dat TensorFlow tren Windows", "OFF"),
    ("Cach cai Docker tren Ubuntu", "OFF"),
    ("Cong thuc nau pho bo", "OFF"),
    ("Gia vang hom nay bao nhieu", "OFF"),
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        on_found = on_total = off_found = off_total = 0
        print("%-52s %-4s %-6s %s" % ("QUERY", "KIND", "N", "VERDICT"))
        print("-" * 78)

        for query, kind in CASES:
            results = await hybrid_search(
                session, query_text=query, user_id=TEST_USER_ID, is_admin=False
            )
            found = len(results) > 0

            if kind == "ON":
                on_total += 1
                on_found += 1 if found else 0
                verdict = "OK" if found else "MISS (đáng lẽ tìm được)"
            else:
                off_total += 1
                off_found += 1 if found else 0
                verdict = "FALSE-HIT (đáng lẽ rỗng)" if found else "OK"

            print("%-52s %-4s %-6s %s" % (query[:52], kind, len(results), verdict))

        print("-" * 78)
        print("Recall  (ON tìm được)   : %d/%d" % (on_found, on_total))
        print("False-hit (OFF lọt lưới): %d/%d" % (off_found, off_total))
        print("Ngưỡng hiện tại         : %.2f" % MIN_RELEVANCE_SIMILARITY)


if __name__ == "__main__":
    asyncio.run(main())
