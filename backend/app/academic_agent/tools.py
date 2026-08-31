"""
Tool registry cho category ACTION_REQUEST (xem app/router_agent/
classifier.py) - định nghĩa MỌI hành động Nova có thể THỰC HIỆN thay
người dùng qua function-calling của OpenAI.

QUYẾT ĐỊNH KIẾN TRÚC: đây CHỈ LÀ schema mô tả tool (tên, mô tả, tham
số) - KHÔNG có logic thực thi ở file này (xem tool_executor.py). Tách
riêng vì 2 lý do khác nhau: schema cần định dạng ĐÚNG chuẩn OpenAI
function-calling (dict JSON Schema thuần) để truyền thẳng vào tham số
`tools=` của API, còn thực thi cần async/DB session/RBAC - trộn chung
sẽ khiến file vừa khó đọc vừa khó test độc lập từng phần.

2 NHÓM tool, theo ĐÚNG ranh giới RBAC của hệ thống (role toàn cục ở
app_user.role - xem app/auth/dependencies.py::require_role):
- TOOLS_INSTRUCTOR: giảng viên/admin - gồm cả tool ĐỌC lẫn tool GHI.
- TOOLS_STUDENT: sinh viên - CHỈ tool ĐỌC, giới hạn xem dữ liệu CỦA
  CHÍNH HỌ (không có tool nào cho sinh viên xem dữ liệu người khác).

Trong nhóm giảng viên, tool GHI (tạo/sửa/xoá dữ liệu) BẮT BUỘC phải
qua bước xác nhận riêng trước khi thực thi (xem TOOLS_REQUIRING_
CONFIRMATION + logic trong agent.py) - đây là ranh giới AN TOÀN CỐT
LÕI của cả tính năng: Nova KHÔNG BAO GIỜ tự ý ghi dữ liệu ngay trong
lượt LLM chọn tool.
"""

# ---------- Tool ĐỌC - GIẢNG VIÊN ----------

_GET_CLASS_ANALYTICS = {
    "type": "function",
    "function": {
        "name": "get_class_analytics",
        "description": (
            "Xem tình hình học tập của TỪNG sinh viên trong 1 lớp: mức độ nắm vững, "
            "khái niệm đang yếu, sinh viên nào cần hỗ trợ. Dùng khi giảng viên hỏi "
            "về tiến độ/tình hình chung của cả lớp hoặc muốn biết ai cần hỗ trợ."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem."},
            },
            "required": ["course_id"],
        },
    },
}

_GET_COURSE_ROSTER = {
    "type": "function",
    "function": {
        "name": "get_course_roster",
        "description": "Xem danh sách sinh viên đang học trong 1 lớp (tên, email, ngày vào lớp).",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem danh sách."},
            },
            "required": ["course_id"],
        },
    },
}

_GET_POPULAR_CONCEPTS = {
    "type": "function",
    "function": {
        "name": "get_popular_concepts",
        "description": (
            "Xem các khái niệm được sinh viên hỏi nhiều nhất trong 1 lớp, kèm độ khớp "
            "tài liệu và tỷ lệ đánh giá tích cực - dùng khi giảng viên muốn biết chủ đề "
            "nào sinh viên quan tâm/gặp khó nhất."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem."},
            },
            "required": ["course_id"],
        },
    },
}

_GET_PENDING_DOCUMENTS = {
    "type": "function",
    "function": {
        "name": "get_pending_documents",
        "description": "Xem danh sách tài liệu đang chờ giảng viên duyệt (chưa khả dụng cho sinh viên) trong 1 lớp.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem tài liệu chờ duyệt."},
            },
            "required": ["course_id"],
        },
    },
}

_GET_ASSIGNMENT_RESULTS = {
    "type": "function",
    "function": {
        "name": "get_assignment_results",
        "description": "Xem kết quả cả lớp của 1 bài tập cụ thể: điểm từng sinh viên, điểm trung bình, khái niệm nào cả lớp làm sai nhiều nhất.",
        "parameters": {
            "type": "object",
            "properties": {
                "assignment_id": {"type": "integer", "description": "ID của bài tập cần xem kết quả."},
            },
            "required": ["assignment_id"],
        },
    },
}

_GET_STUDENT_ASSIGNMENT_DETAILS = {
    "type": "function",
    "function": {
        "name": "get_student_assignment_details",
        "description": (
            "Xem chi tiết các câu làm sai trong bài nộp CHÍNH THỨC của đúng một "
            "sinh viên. Chỉ dùng khi giảng viên hỏi đích danh sinh viên; không dùng "
            "để quét chi tiết cả lớp và không đọc lịch sử chat Nova."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID lớp do giảng viên phụ trách."},
                "student_id": {"type": "integer", "description": "ID của đúng một sinh viên."},
                "assignment_id": {"type": "integer", "description": "ID bài tập để lọc hẹp (tùy chọn)."},
            },
            "required": ["course_id", "student_id"],
        },
    },
}

_DRAFT_ASSIGNMENT_REMINDER = {
    "type": "function",
    "function": {
        "name": "draft_assignment_reminder",
        "description": (
            "Soạn BẢN NHÁP nhắc bài tập từ dữ liệu thật để giảng viên tự sao chép. "
            "Tool không gửi email, thông báo hay tin nhắn cho sinh viên."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "assignment_id": {"type": "integer", "description": "ID bài tập cần soạn lời nhắc."},
            },
            "required": ["assignment_id"],
        },
    },
}

_GET_TEACHING_RECOMMENDATIONS = {
    "type": "function",
    "function": {
        "name": "get_teaching_recommendations",
        "description": (
            "Tạo gợi ý lộ trình giảng dạy từ mastery và khoảng trống khái niệm tổng hợp của lớp. "
            "Trả riêng dữ kiện và đề xuất; không đọc chat riêng hay tự gắn nhãn sinh viên."
        ),
        "parameters": {
            "type": "object",
            "properties": {"course_id": {"type": "integer", "description": "ID lớp do giảng viên phụ trách."}},
            "required": ["course_id"],
        },
    },
}

_GET_COSTS = {
    "type": "function",
    "function": {
        "name": "get_costs",
        "description": "Xem chi phí sử dụng AI (LLM) đã phát sinh cho 1 lớp - tổng chi phí, chi phí trung bình mỗi câu hỏi, dự báo chi phí hàng tháng.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem chi phí."},
            },
            "required": ["course_id"],
        },
    },
}

_GET_PIPELINE_TIMING = {
    "type": "function",
    "function": {
        "name": "get_pipeline_timing",
        "description": "Xem thời gian xử lý trung bình của từng bước trong pipeline trả lời câu hỏi (kiểm tra an toàn, tìm tài liệu, sinh câu trả lời) cho 1 lớp - dùng để biết bước nào đang chậm.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem."},
            },
            "required": ["course_id"],
        },
    },
}

# ---------- Tool ĐỌC - SINH VIÊN ----------

_GET_MY_MASTERY = {
    "type": "function",
    "function": {
        "name": "get_my_mastery",
        "description": "Xem mức độ nắm vững (mastery) CỦA CHÍNH MÌNH cho từng khái niệm trong 1 lớp học.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem tiến độ."},
            },
            "required": ["course_id"],
        },
    },
}

_GET_MY_ASSIGNMENTS = {
    "type": "function",
    "function": {
        "name": "get_my_assignments",
        "description": "Xem danh sách bài tập của 1 lớp kèm trạng thái đã nộp/chưa nộp và điểm số CỦA CHÍNH MÌNH.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem bài tập."},
            },
            "required": ["course_id"],
        },
    },
}

_GET_LEARNING_PATH = {
    "type": "function",
    "function": {
        "name": "get_learning_path",
        "description": "Xem lộ trình học tập CỦA CHÍNH MÌNH trong 1 lớp: khái niệm nào đã hoàn thành, đang học, nên học tiếp theo.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần xem lộ trình."},
            },
            "required": ["course_id"],
        },
    },
}

_GET_MY_WEAKEST_CONCEPT = {
    "type": "function",
    "function": {
        "name": "get_my_weakest_concept",
        "description": "Xem khái niệm CỦA CHÍNH MÌNH đang yếu nhất (trên mọi lớp đã tham gia) - dùng khi sinh viên hỏi mình đang yếu ở đâu, nên ôn tập gì.",
        "parameters": {"type": "object", "properties": {}},
    },
}

_GET_MY_RECENT_MISTAKES = {
    "type": "function",
    "function": {
        "name": "get_my_recent_mistakes",
        "description": (
            "Xem các câu quiz CỦA CHÍNH MÌNH đã làm SAI gần đây nhất, kèm đáp án đã chọn, "
            "đáp án đúng và giải thích - dùng khi sinh viên hỏi mình hay làm sai câu nào, "
            "muốn xem lại các câu đã làm sai để ôn tập."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "integer",
                    "description": "ID lớp học muốn lọc (tuỳ chọn) - bỏ trống để xem của mọi lớp.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Số câu tối đa muốn xem, mặc định 5.",
                },
            },
        },
    },
}

_EXPLAIN_MY_ANSWER = {
    "type": "function",
    "function": {
        "name": "explain_my_answer",
        "description": (
            "Giải thích chi tiết 1 câu quiz CỤ THỂ mà CHÍNH MÌNH đã từng làm - dùng khi "
            "sinh viên hỏi 'giải thích đáp án câu X', biết rõ ID câu hỏi cần giải thích."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quiz_question_id": {"type": "integer", "description": "ID của câu hỏi quiz cần giải thích."},
            },
            "required": ["quiz_question_id"],
        },
    },
}

# ---------- Tool GHI - GIẢNG VIÊN (BẮT BUỘC xác nhận) ----------

_CREATE_CONCEPT = {
    "type": "function",
    "function": {
        "name": "create_concept",
        "description": "Tạo 1 khái niệm học thuật mới cho 1 lớp - dùng khi giảng viên yêu cầu thêm/tạo khái niệm mới.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học sẽ chứa khái niệm này."},
                "name": {"type": "string", "description": "Tên khái niệm, vd 'Đệ quy', 'Con trỏ'."},
                "complexity": {
                    "type": "integer",
                    "description": "Độ khó từ 1 (dễ nhất) tới 5 (khó nhất). Mặc định 3 nếu không được nêu rõ.",
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": ["course_id", "name"],
        },
    },
}

_CREATE_ASSIGNMENT = {
    "type": "function",
    "function": {
        "name": "create_assignment",
        "description": (
            "Giao 1 bài tập trắc nghiệm mới cho lớp, dựa trên danh sách khái niệm chỉ định "
            "(hệ thống tự lấy/sinh câu hỏi cho từng khái niệm) - dùng khi giảng viên yêu cầu "
            "giao/tạo bài tập."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học sẽ nhận bài tập."},
                "title": {"type": "string", "description": "Tiêu đề bài tập."},
                "concept_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Danh sách ID các khái niệm cần ra đề, mỗi khái niệm sẽ có 1 câu hỏi.",
                },
                "description": {"type": "string", "description": "Mô tả thêm cho bài tập (tuỳ chọn)."},
            },
            "required": ["course_id", "title", "concept_ids"],
        },
    },
}

_APPROVE_DOCUMENT = {
    "type": "function",
    "function": {
        "name": "approve_document",
        "description": "Duyệt 1 tài liệu đang chờ duyệt (PENDING_REVIEW) - sau khi duyệt, tài liệu khả dụng cho sinh viên tra cứu.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "ID của tài liệu cần duyệt."},
            },
            "required": ["document_id"],
        },
    },
}

_REJECT_DOCUMENT = {
    "type": "function",
    "function": {
        "name": "reject_document",
        "description": "Từ chối 1 tài liệu đang chờ duyệt - tài liệu sẽ KHÔNG khả dụng cho sinh viên tra cứu.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "ID của tài liệu cần từ chối."},
                "reason": {"type": "string", "description": "Lý do từ chối (tuỳ chọn)."},
            },
            "required": ["document_id"],
        },
    },
}

_REMOVE_STUDENT_FROM_COURSE = {
    "type": "function",
    "function": {
        "name": "remove_student_from_course",
        "description": "Gỡ 1 sinh viên khỏi lớp (unenroll) - sinh viên vẫn giữ tài khoản, chỉ không còn thuộc lớp này nữa.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học."},
                "student_user_id": {"type": "integer", "description": "ID tài khoản của sinh viên cần gỡ khỏi lớp."},
            },
            "required": ["course_id", "student_user_id"],
        },
    },
}

_ENROLL_STUDENT = {
    "type": "function",
    "function": {
        "name": "enroll_student",
        "description": "Thêm 1 sinh viên (theo email) vào lớp - sinh viên phải đã có tài khoản trong hệ thống.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_id": {"type": "integer", "description": "ID của lớp học cần thêm sinh viên vào."},
                "student_email": {"type": "string", "description": "Email tài khoản của sinh viên cần thêm."},
            },
            "required": ["course_id", "student_email"],
        },
    },
}

_CREATE_COURSE = {
    "type": "function",
    "function": {
        "name": "create_course",
        "description": "Tạo 1 lớp học mới - người tạo tự động trở thành giáo viên phụ trách lớp.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Mã lớp, vd 'CS301-T7'."},
                "name": {"type": "string", "description": "Tên lớp, vd 'Nhập môn Lập trình - Lớp thứ 7'."},
            },
            "required": ["code", "name"],
        },
    },
}

TOOLS_INSTRUCTOR: list[dict] = [
    _GET_CLASS_ANALYTICS,
    _GET_COURSE_ROSTER,
    _GET_POPULAR_CONCEPTS,
    _GET_PENDING_DOCUMENTS,
    _GET_ASSIGNMENT_RESULTS,
    _GET_STUDENT_ASSIGNMENT_DETAILS,
    _DRAFT_ASSIGNMENT_REMINDER,
    _GET_TEACHING_RECOMMENDATIONS,
    _GET_COSTS,
    _GET_PIPELINE_TIMING,
    _CREATE_CONCEPT,
    _CREATE_ASSIGNMENT,
    _APPROVE_DOCUMENT,
    _REJECT_DOCUMENT,
    _REMOVE_STUDENT_FROM_COURSE,
    _ENROLL_STUDENT,
    _CREATE_COURSE,
]

TOOLS_STUDENT: list[dict] = [
    _GET_MY_MASTERY,
    _GET_MY_ASSIGNMENTS,
    _GET_LEARNING_PATH,
    _GET_MY_WEAKEST_CONCEPT,
    _GET_MY_RECENT_MISTAKES,
    _EXPLAIN_MY_ANSWER,
]


def get_tools_for_role(role: str) -> list[dict]:
    """
    Trả về đúng bộ tool cho role đang gọi - đây CHỈ LÀ bước lọc THUẬN
    TIỆN để LLM không thấy tool ngoài phạm vi của mình (giảm khả năng
    tự "gợi ý" chọn nhầm tool). KHÔNG PHẢI lớp bảo mật - RBAC thật sự
    được kiểm tra LẠI trong tool_executor.py, không tin role/quyền mà
    LLM ngầm giả định (xem docstring execute_tool()).
    """
    if role in ("INSTRUCTOR", "ADMIN"):
        return TOOLS_INSTRUCTOR
    if role == "STUDENT":
        return TOOLS_STUDENT
    return []


# Tool GHI (tạo/sửa/xoá dữ liệu) - BẮT BUỘC người dùng xác nhận trước
# khi thực thi (xem agent.py, nhánh xử lý ACTION_REQUEST). Toàn bộ tool
# ĐỌC (kể cả của giảng viên lẫn sinh viên) KHÔNG có trong tập này -
# thực thi ngay, không cần hỏi lại, vì không làm thay đổi dữ liệu nào.
TOOLS_REQUIRING_CONFIRMATION: set[str] = {
    "create_concept",
    "create_assignment",
    "approve_document",
    "reject_document",
    "remove_student_from_course",
    "enroll_student",
    "create_course",
}

# Nhãn tiếng Việt ngắn gọn cho từng tool - dùng hiển thị UI (câu hỏi xác
# nhận, lịch sử hành động...). PHẢI có đủ nhãn cho MỌI tool (đọc lẫn ghi).
TOOL_LABELS_VI: dict[str, str] = {
    "get_class_analytics": "Xem tình hình học tập của lớp",
    "get_course_roster": "Xem danh sách sinh viên",
    "get_popular_concepts": "Xem khái niệm được hỏi nhiều nhất",
    "get_pending_documents": "Xem tài liệu chờ duyệt",
    "get_assignment_results": "Xem kết quả bài tập",
    "get_student_assignment_details": "Xem chi tiết bài làm của một sinh viên",
    "draft_assignment_reminder": "Soạn bản nháp nhắc bài tập",
    "get_teaching_recommendations": "Gợi ý lộ trình giảng dạy",
    "get_costs": "Xem chi phí sử dụng AI",
    "get_pipeline_timing": "Xem thời gian xử lý hệ thống",
    "get_my_mastery": "Xem tiến độ nắm vững của bạn",
    "get_my_assignments": "Xem bài tập của bạn",
    "get_learning_path": "Xem lộ trình học tập của bạn",
    "get_my_weakest_concept": "Xem khái niệm bạn đang yếu nhất",
    "get_my_recent_mistakes": "Xem các câu bạn làm sai gần đây",
    "explain_my_answer": "Giải thích đáp án câu bạn đã làm",
    "create_concept": "Tạo khái niệm mới",
    "create_assignment": "Giao bài tập mới",
    "approve_document": "Duyệt tài liệu",
    "reject_document": "Từ chối tài liệu",
    "remove_student_from_course": "Gỡ sinh viên khỏi lớp",
    "enroll_student": "Thêm sinh viên vào lớp",
    "create_course": "Tạo lớp học mới",
}
