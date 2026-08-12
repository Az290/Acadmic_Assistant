"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { UserRole } from "@/lib/api";

const ROLE_LABEL: Record<UserRole, string> = {
  STUDENT: "Sinh viên",
  INSTRUCTOR: "Giảng viên",
  ADMIN: "Quản trị viên",
};

// Tiêu đề trang theo route. Thứ tự trong object QUAN TRỌNG với các route
// lồng nhau: "/admin/eval" phải đứng TRƯỚC "/admin", nếu không tiền tố
// "/admin" sẽ khớp trước và trang eval hiện sai tên.
const PAGE_TITLE: Record<string, string> = {
  "/admin/eval": "Đánh giá chất lượng",
  "/student": "Trang chủ",
  "/mastery": "Tiến độ học tập",
  "/history": "Lịch sử hỏi đáp",
  "/quiz": "Quiz ôn tập",
  "/profile": "Hồ sơ cá nhân",
  "/instructor": "Thống kê lớp",
  "/assignments": "Bài tập",
  "/review": "Duyệt tài liệu",
  "/admin": "Quản trị hệ thống",
  "/courses": "Lớp học",
  "/documents": "Tài liệu",
};

function pageTitleFor(pathname: string): string {
  const match = Object.keys(PAGE_TITLE).find((prefix) => pathname.startsWith(prefix));
  return match ? PAGE_TITLE[match] : "Academic Assistant";
}

/** Chữ cái đầu của tên - dùng làm avatar thay vì viết tắt vai trò
 *  ("SV"/"GV"), vì người dùng nhận ra CHÍNH MÌNH nhanh hơn qua tên. */
function initialOf(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  return (parts[parts.length - 1]?.[0] ?? "?").toUpperCase();
}

export default function Topbar() {
  const { user } = useAuth();
  const pathname = usePathname();

  if (!user) return null;

  return (
    <header
      className="flex h-14 flex-shrink-0 items-center justify-between border-b px-7"
      style={{ borderColor: "var(--border)", background: "var(--panel)" }}
    >
      <h1 className="text-page-title m-0">{pageTitleFor(pathname)}</h1>

      {/* Đã bỏ nhãn "● Online": người dùng đang nhìn thấy giao diện thì
          hiển nhiên là đang kết nối - nhãn đó chiếm chỗ mà không mang
          thông tin nào. */}
      <div className="flex items-center gap-2.5">
        <span className="text-support hidden sm:block">{user.full_name}</span>
        <div
          className="flex h-7 w-7 items-center justify-center rounded-full text-[11.5px] font-semibold"
          style={{ background: "var(--accent-bg)", color: "var(--accent-ink)" }}
          title={`${user.full_name} · ${ROLE_LABEL[user.role]}`}
        >
          {initialOf(user.full_name)}
        </div>
      </div>
    </header>
  );
}
