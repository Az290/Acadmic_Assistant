"""
QUYỀN ĐỌC ĐOẠN TÀI LIỆU - định nghĩa ở ĐÚNG MỘT NƠI cho toàn hệ thống.

VÌ SAO TÁCH RIÊNG: có nhiều đường dẫn khác nhau dẫn tới cùng một nội
dung - tìm kiếm (hybrid_search), xem trích dẫn (/v1/chunks/{id}), và
sau này có thể thêm nữa. Nếu mỗi nơi tự viết mệnh đề WHERE riêng, chỉ
cần một nơi quên một điều kiện là rò rỉ dữ liệu, mà lỗi kiểu đó rất
khó phát hiện (chức năng vẫn "chạy đúng", chỉ là trả về nhiều hơn mức
được phép).

Mọi thay đổi về quyền đọc tài liệu PHẢI sửa ở file này, không sửa rải
rác trong từng endpoint.
"""

# 3 điều kiện nền:
#
# 1. course_id thuộc lớp đã ghi danh - không ai đọc được tài liệu lớp
#    mình không tham gia. NGOẠI LỆ DUY NHẤT: ADMIN, vì họ có quyền toàn
#    hệ thống và không ghi danh lớp nào cả (nếu bắt buộc enrollment thì
#    ADMIN sẽ không đọc được gì) - nhất quán với _require_course_owner()
#    ở app/instructor/router.py, nơi ADMIN cũng bỏ qua kiểm tra chủ lớp.
# 2. is_solution = FALSE - đoạn chứa lời giải bài tập không bao giờ lọt
#    vào ngữ cảnh trả lời, tránh AI đọc đáp án rồi đưa thẳng cho học sinh.
# 3. document.status = 'APPROVED' - tài liệu chưa qua kiểm duyệt của
#    giảng viên (HITL) không được dùng để trả lời.
#
# visibility (COURSE / INSTRUCTOR_ONLY) được xử lý riêng bên dưới vì
# điều kiện phụ thuộc vào vai trò người đọc.
_BASE_CONDITIONS = """
    EXISTS (
        SELECT 1
        FROM document_course dc
        WHERE dc.document_id = chunk.document_id
          AND (
              {is_admin}
              OR dc.course_id IN (
                  SELECT course_id FROM enrollment WHERE user_id = {user_id}
              )
          )
    )
    AND chunk.is_solution = FALSE
    AND chunk.document_id IN (SELECT id FROM document WHERE status = 'APPROVED')
"""

# Đoạn đánh dấu INSTRUCTOR_ONLY (đề thi, đáp án, tài liệu nội bộ) chỉ
# đọc được bởi:
#   - ADMIN: quyền toàn hệ thống, nhất quán với mọi endpoint khác
#     (_require_course_owner cũng cho ADMIN đi qua).
#   - Giảng viên CỦA CHÍNH LỚP ĐÓ: kiểm tra qua enrollment với
#     role_in_course='INSTRUCTOR', KHÔNG PHẢI chỉ dựa vào role toàn cục.
#     Một giảng viên lớp A tuyệt đối không đọc được tài liệu nội bộ của
#     lớp B dù họ cũng mang vai trò INSTRUCTOR trong hệ thống.
_VISIBILITY_CONDITION = """
    AND (
        chunk.visibility = 'COURSE'
        OR (
            chunk.visibility = 'INSTRUCTOR_ONLY'
            AND (
                {is_admin}
                OR EXISTS (
                    SELECT 1 FROM document_course dc
                    JOIN course c ON c.id = dc.course_id
                    WHERE dc.document_id = chunk.document_id
                      AND (
                          c.owner_id = {user_id}
                          OR dc.course_id IN (
                              SELECT course_id FROM enrollment
                              WHERE user_id = {user_id} AND role_in_course = 'INSTRUCTOR'
                          )
                      )
                )
            )
        )
    )
"""


def chunk_access_sql(*, user_id_param: str = ":user_id", is_admin_param: str = ":is_admin") -> str:
    """
    Mệnh đề SQL lọc quyền đọc chunk - ghép vào sau WHERE của câu truy vấn.

    Nơi gọi BẮT BUỘC truyền 2 giá trị tương ứng: id người đọc và cờ
    người đó có phải ADMIN hay không.

    2 tham số của hàm này để chọn KIỂU PLACEHOLDER, vì trong cùng dự án
    có 2 cách truyền tham số vào SQL:
      - session.execute(text(...))  -> tham số TÊN   (mặc định :user_id)
      - conn.exec_driver_sql(...)   -> tham số VỊ TRÍ ($1, $2...)
    Nhờ vậy 2 kiểu gọi khác nhau vẫn dùng CHUNG một định nghĩa quyền,
    thay vì mỗi bên giữ một bản sao dễ lệch nhau khi sửa (đây từng là
    tình trạng thật của file hybrid_search.py trước khi tách module này).

    Placeholder được ghép bằng .format() - AN TOÀN vì giá trị truyền vào
    do CHÍNH CODE quy định (":user_id" hoặc "$2"), không bao giờ đến từ
    dữ liệu người dùng; giá trị thật của user_id vẫn đi qua cơ chế tham
    số hoá của driver, không nối chuỗi.
    """
    return (_BASE_CONDITIONS + _VISIBILITY_CONDITION).format(
        user_id=user_id_param, is_admin=is_admin_param
    )
