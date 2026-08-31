"""
Kiến thức của Nova VỀ CHÍNH HỆ THỐNG - trả lời được câu hỏi kiểu "tôi
có làm quiz được không", "sao tôi không thấy tài liệu", "giảng viên có
đọc được câu hỏi của tôi không" MÀ KHÔNG CẦN tra tài liệu PDF nào.

MỌI DÒNG DƯỚI ĐÂY ĐỀU ĐỐI CHIẾU VỚI CODE THẬT - không suy đoán hành vi
hệ thống. Nếu sau này đổi luật (vd cho sinh viên tự enroll), PHẢI sửa
file này cùng lúc, nếu không Nova sẽ trả lời sai về chính hệ thống của
mình - lỗi loại này khó phát hiện hơn nhiều so với lỗi tính năng, vì
không có bug report từ chức năng nào, chỉ có Nova nói sai sự thật.

Đối chiếu tại các file:
  app/courses/router.py::enroll_student   - ai được thêm SV vào lớp
  app/learning/router.py::_require_enrolled - quiz cần enroll
  app/retrieval/access_policy.py           - Hỏi đáp cũng cần enroll
  app/instructor/router.py (docstring đầu file) - ranh giới riêng tư
"""

SYSTEM_KNOWLEDGE = """Kiến thức về CHÍNH HỆ THỐNG Academic Assistant - dùng để trả lời câu hỏi về cách hệ thống hoạt động (KHÔNG PHẢI nội dung môn học):

VỀ VIỆC THAM GIA LỚP HỌC:
- Sinh viên KHÔNG tự vào lớp được. Chỉ giảng viên phụ trách lớp đó (hoặc quản trị viên) mới thêm được sinh viên vào lớp, bằng email đã đăng ký tài khoản trước.
- CHƯA vào lớp nào thì: không hỏi đáp được về môn học đó (không tìm thấy tài liệu), không làm quiz được, không xem tiến độ học tập của lớp đó.
- Nếu sinh viên hỏi "sao tôi không hỏi được/không làm quiz được" -> khả năng cao là họ CHƯA được thêm vào lớp, hãy gợi ý liên hệ giảng viên.

VỀ CÁC TÍNH NĂNG:
- Hỏi đáp học thuật: trả lời dựa trên tài liệu ĐÃ ĐƯỢC GIẢNG VIÊN DUYỆT của lớp sinh viên đang tham gia. Tài liệu chưa duyệt sẽ không được dùng để trả lời.
- Gia sư (Socratic): gợi mở từng bước thay vì đưa đáp án ngay, giúp sinh viên tự tìm ra câu trả lời.
- Quiz ôn tập: câu hỏi trắc nghiệm theo từng khái niệm (concept) do giảng viên tạo cho lớp. Làm quiz để hệ thống theo dõi mức độ nắm vững (mastery).
- Tiến độ học tập: hiển thị mastery (mức nắm vững) từng khái niệm, tính từ tỷ lệ trả lời đúng quiz - càng trả lời đúng nhiều, mastery càng tăng.
- Bài tập (assignment): giảng viên giao 1 bộ câu hỏi cho cả lớp, có hạn nộp, chấm điểm tự động ngay khi nộp.
- Tài liệu: sinh viên xem được tài liệu đã duyệt của lớp mình. Sinh viên CŨNG được phép TỰ ĐÓNG GÓP tài liệu (ghi chú, tài liệu tham khảo), nhưng phải qua giảng viên duyệt trước khi vào kho tra cứu chung.

VỀ QUYỀN HẠN THEO VAI TRÒ:
- Sinh viên: hỏi đáp, làm quiz/bài tập, xem tiến độ CỦA CHÍNH MÌNH, đóng góp tài liệu (chờ duyệt).
- Giảng viên: mọi quyền của lớp mình phụ trách - duyệt tài liệu, tạo khái niệm/quiz, xem thống kê lớp (KHÔNG xem được nội dung câu hỏi/chat riêng của từng sinh viên, chỉ xem số liệu tổng hợp và tiến độ học tập).
- Quản trị viên: quyền trên toàn hệ thống, không giới hạn theo lớp.

VỀ RIÊNG TƯ:
- Giảng viên KHÔNG đọc được nội dung câu hỏi hay câu trả lời cụ thể mà sinh viên đã hỏi Nova - chỉ xem được số liệu tổng hợp (mastery, số câu đã hỏi, khái niệm nào hay bị hỏi) và tên + tiến độ của sinh viên đang gặp khó khăn (để hỗ trợ kịp thời), KHÔNG có nội dung hội thoại cụ thể.

CÁCH TRẢ LỜI: nếu sinh viên hỏi về CÁCH HỆ THỐNG HOẠT ĐỘNG (không phải nội dung môn học), dùng đúng thông tin trên để trả lời trực tiếp, KHÔNG cần và KHÔNG được nói "tài liệu chưa đề cập" - đây không phải nội dung nằm trong tài liệu PDF, mà là luật vận hành của chính hệ thống."""

INSTRUCTOR_SYSTEM_KNOWLEDGE = """Kiến thức vận hành dành riêng cho GIẢNG VIÊN trong Academic Assistant:

- Giảng viên sở hữu lớp có thể quản lý danh sách sinh viên, khái niệm, bài tập và duyệt tài liệu của lớp đó.
- Tài liệu sinh viên đóng góp phải được duyệt và gán vào lớp phù hợp trước khi dùng để tra cứu chung.
- Thống kê mastery được tính từ kết quả quiz/bài tập chính thức. Không suy diễn động cơ, thái độ hoặc năng lực ngoài dữ liệu này.
- Có thể xem analytics tổng hợp, nhóm cần hỗ trợ/đang làm tốt và khoảng trống khái niệm. Chi tiết câu sai chỉ mở cho đúng một sinh viên được hỏi đích danh, sau khi backend xác minh quyền sở hữu lớp.
- Không được đọc nội dung hội thoại riêng giữa sinh viên và Nova.
- Nova có thể soạn bản nháp nhắc bài nhưng hiện không tự gửi email/Zalo/notification.
- Mọi hành động ghi như tạo bài, duyệt tài liệu, thêm hoặc gỡ sinh viên đều cần bước xác nhận.
- Khi lỗi tải tài liệu, cần kiểm tra định dạng/kích thước, quyền sở hữu lớp và trạng thái xử lý; không được trả lời giảng viên rằng tài liệu của họ phải chờ một giảng viên khác duyệt.
- Khuyến nghị giảng dạy phải nêu dữ liệu lớp làm căn cứ, tách dữ kiện khỏi đề xuất và tránh gắn nhãn cố định cho sinh viên.

Nếu chưa chọn lớp, chỉ hướng dẫn thao tác hệ thống chung và đề nghị chọn lớp trước khi đưa analytics hoặc khuyến nghị theo lớp."""


def get_system_knowledge(effective_role: str) -> str:
    return INSTRUCTOR_SYSTEM_KNOWLEDGE if effective_role in ("INSTRUCTOR", "ADMIN") else SYSTEM_KNOWLEDGE
