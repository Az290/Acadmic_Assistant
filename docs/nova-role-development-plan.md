# Kế hoạch phát triển Nova theo vai trò

Tài liệu này mô tả hướng phát triển để thảo luận và chốt trước khi code.

**Trạng thái hiện tại:** nền tảng tách theo vai trò ĐÃ có ở tầng dữ liệu và
tool. Phần CHƯA có là tách prompt/policy tường minh theo vai trò, hành vi
cảnh báo hạn nộp, và bộ eval riêng cho từng vai trò.

## Nền tảng đã có trong production

- Backend xác định vai trò từ tài khoản đã xác thực, không nhận role do
  frontend gửi lên.
- `load_student_context()` chặn ngay theo role: chỉ nạp hồ sơ tiến độ khi
  `user_role == "STUDENT"`, các vai trò khác trả về context rỗng.
- `build_learning_progress_block()` đã bơm vào prompt cho sinh viên: danh
  sách bài đã nộp/chưa nộp, cờ **QUÁ HẠN**, hạn nộp, điểm từng bài, và chi
  tiết đúng/sai của các lần nộp gần đây. Khối này gắn vào phần đầu prompt
  nên áp dụng cho mọi category, không riêng hỏi đáp.
- `build_recent_mistake_block()` bơm câu quiz sai gần nhất, chỉ cho
  `RAG_QUESTION` và `SOCRATIC_REQUEST`.
- Tool đã phân theo vai trò ở backend: 6 tool đọc dữ liệu cá nhân cho sinh
  viên, 7 tool đọc dữ liệu lớp + 7 tool ghi cho giảng viên; `get_tools_for_role()`
  lọc danh sách, `tool_executor.py` kiểm tra lại quyền sở hữu lớp cho từng
  lần gọi.
- `AgentActionLog` ghi mọi hành động GHI dữ liệu Nova thực hiện thay giảng
  viên (thành công lẫn thất bại).
- Ranh giới riêng tư đang được giữ: giảng viên chỉ truy cập dữ liệu lớp mình
  sở hữu, sinh viên chỉ truy cập dữ liệu của chính mình.

## Phần còn thiếu, cần chốt rồi làm

### 1. Nova dành cho sinh viên

- Vai trò chính: trợ giảng cá nhân và người nhắc tiến độ.
- Ưu tiên trả lời dựa trên tài liệu lớp, giải thích lỗi sai và đề xuất bước
  học tiếp theo.
- Cảnh báo bài quá hạn hoặc sắp đến hạn khi câu hỏi có liên quan; không lặp
  cảnh báo trong mọi tin nhắn.
- Không tiết lộ đáp án bài chưa nộp và không làm bài thay sinh viên.
- Cho phép hỏi: "Tôi còn bài nào?", "Tôi yếu phần nào?", "Giải thích câu tôi
  làm sai".

### 2. Nova dành cho giảng viên

- Vai trò chính: trợ lý vận hành lớp và phân tích sư phạm.
- Ưu tiên dữ liệu tổng hợp của lớp, danh sách sinh viên cần hỗ trợ và khoảng
  trống tài liệu.
- Có thể hỗ trợ soạn/duyệt bài, xem tỷ lệ nộp và đề xuất nội dung ôn tập chung.
- Không đọc nội dung chat riêng của sinh viên và không suy diễn động cơ/năng
  lực ngoài dữ liệu học tập.
- Hành động ghi dữ liệu vẫn phải yêu cầu xác nhận trước khi thực thi.

### 3. Kiến trúc đề xuất

- Tách `StudentAssistantPolicy` và `InstructorAssistantPolicy` ở tầng
  prompt/policy — hiện hai vai trò dùng chung một bộ prompt theo category,
  khác biệt mới chỉ đến từ dữ liệu context được nạp.
- Giữ nguyên nguyên tắc đã áp dụng: tách hàm dựng context theo vai trò,
  KHÔNG dùng một block dữ liệu chung rồi yêu cầu LLM tự lọc.
- Danh sách tool tiếp tục phân quyền ở backend bằng role và quyền sở hữu lớp.
- Mở rộng audit log **có chọn lọc**: chỉ ghi thêm các lần Nova ĐỌC dữ liệu
  gắn danh tính sinh viên cụ thể (`get_class_analytics`, `get_course_roster`).
  Không ghi các tool thống kê tổng hợp (`get_costs`, `get_popular_concepts`,
  `get_pipeline_timing`) vì mỗi câu hỏi thường lệ sẽ đẻ một dòng log, làm
  bảng phình nhanh trong khi giá trị điều tra thấp.
- Xây eval riêng cho từng vai trò: độ chính xác dữ liệu, riêng tư, mức hữu
  ích và hành vi từ chối.

## Các quyết định cần bàn trước khi code

1. Nova có chủ động hiện cảnh báo khi mở chat, hay chỉ cảnh báo sau khi sinh
   viên gửi câu hỏi?
   *Đề xuất: chỉ cảnh báo khi câu hỏi có liên quan. Hệ thống đã có
   `WeakestConceptToast` làm việc nhắc chủ động; để Nova nhắc thêm sẽ trùng
   lặp và gây phiền.*
2. "Sắp đến hạn" được tính là 24 giờ, 48 giờ hay cấu hình theo lớp?
3. Giảng viên được xem chi tiết câu sai của từng sinh viên hay chỉ số liệu
   theo khái niệm?
4. Nova được phép gửi nhắc nhở tự động hay chỉ soạn nội dung để giảng viên
   xác nhận gửi?
5. Sinh viên có được xem đáp án/giải thích của bài đã quá hạn nhưng chưa nộp
   không?
   *Đề xuất: có, kèm ghi chú rõ "bài này chưa nộp nên không tính điểm". Mục
   tiêu hệ thống là học chứ không phải chấm điểm; chặn đáp án sau hạn chỉ
   đẩy sinh viên sang công cụ ngoài, vừa mất tác dụng sư phạm vừa mất dữ liệu.*
6. Cách xưng hô và mức độ chủ động của Nova cho từng vai trò nên trang trọng
   đến đâu?
7. Người dùng có role toàn cục `INSTRUCTOR` nhưng tham gia một lớp với tư cách
   học viên thì Nova xử sự theo vai trò nào trong lớp đó?
   *Bảng `Enrollment` đã tách `role_in_course` khỏi role toàn cục để hỗ trợ
   trường hợp này, nhưng hiện `load_student_context()` chỉ xét role toàn cục
   nên họ sẽ không nhận được hồ sơ tiến độ ở lớp đang học.*

## Trình tự triển khai sau khi chốt

1. Chốt ma trận quyền và hành vi cho từng vai trò (gồm cả trường hợp xung đột
   vai trò ở câu hỏi 7).
2. Tách policy/prompt theo role; context builder đã tách sẵn, chỉ cần bổ sung
   nhánh cho giảng viên.
3. Bổ sung API hoặc tool còn thiếu, kèm kiểm tra quyền sở hữu.
4. Thiết kế UI cảnh báo/insight khác nhau cho sinh viên và giảng viên.
5. Viết eval chống rò rỉ dữ liệu chéo vai trò và test câu hỏi nghiệp vụ thực tế.
6. Chạy thử với dữ liệu demo, duyệt câu trả lời mẫu rồi mới bật mặc định.
