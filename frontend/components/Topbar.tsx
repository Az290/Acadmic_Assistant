"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { UserRole } from "@/lib/api";

const ROLE_LABEL: Record<UserRole, string> = {
  STUDENT: "Sinh viên",
  INSTRUCTOR: "Giảng viên",
  ADMIN: "Quản trị viên",
};

const ROLE_AVATAR: Record<UserRole, string> = {
  STUDENT: "SV",
  INSTRUCTOR: "GV",
  ADMIN: "AD",
};

// Tiêu đề trang theo route - đơn giản hơn NAV có group của prototype
// (app hiện chỉ có 2 trang chính), mở rộng dict này khi thêm trang mới.
const PAGE_TITLE: Record<string, string> = {
  "/student": "Trang chủ",
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

export default function Topbar() {
  const { user } = useAuth();
  const pathname = usePathname();

  if (!user) return null;

  return (
    <div
      className="flex h-[54px] flex-shrink-0 items-center justify-between border-b px-[26px]"
      style={{ borderColor: "var(--border)", background: "var(--panel)" }}
    >
      <div>
        <div className="text-xs" style={{ color: "var(--ink-faint)" }}>
          {ROLE_LABEL[user.role]}
        </div>
        <h1 className="m-0 text-[16px] font-bold">{pageTitleFor(pathname)}</h1>
      </div>
      <div className="flex items-center gap-3.5">
        <span
          className="inline-block rounded-full px-2.5 py-[3px] text-[10.5px] font-bold"
          style={{ background: "var(--accent-bg)", color: "var(--accent-ink)" }}
        >
          ● Online
        </span>
        <div
          className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold"
          style={{ background: "var(--accent-bg)", color: "var(--accent-ink)" }}
        >
          {ROLE_AVATAR[user.role]}
        </div>
      </div>
    </div>
  );
}
