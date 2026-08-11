"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { UserRole } from "@/lib/api";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  // roles: nếu để trống, MỌI role đã đăng nhập đều thấy mục này -
  // liệt kê rõ ràng role nào thấy mục nào thay vì để mặc định "ai
  // cũng thấy", tránh lộ chức năng quản trị cho STUDENT dù API đã
  // chặn ở tầng backend (đây là lớp UX, không phải lớp bảo mật -
  // backend vẫn là nơi thật sự chặn quyền truy cập).
  roles?: UserRole[];
}

// Icon SVG lấy đúng bộ "feather-style" (stroke, không fill) dùng
// trong prototype - giữ file gọn bằng cách định nghĩa dạng hàm nhỏ
// thay vì import thư viện icon ngoài (không cần thêm dependency chỉ
// để có vài icon cố định).
function IconCourses() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IconDocuments() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  );
}

function IconHome() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  );
}

function IconChart() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

function IconAssignment() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 2h6a1 1 0 0 1 1 1v2H8V3a1 1 0 0 1 1-1z" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 11l3 3L22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  );
}

function IconShield() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

// Mỗi role vào ĐÚNG dashboard của mình (yêu cầu đã chốt từ Tác vụ #3):
// trang chủ khác nhau hoàn toàn theo vai trò, không phải 1 giao diện
// chung có nút chuyển role.
const NAV_ITEMS: NavItem[] = [
  { href: "/student", label: "Trang chủ", icon: <IconHome />, roles: ["STUDENT"] },
  { href: "/instructor", label: "Thống kê lớp", icon: <IconChart />, roles: ["INSTRUCTOR", "ADMIN"] },
  { href: "/assignments", label: "Bài tập", icon: <IconAssignment /> },
  { href: "/review", label: "Duyệt tài liệu", icon: <IconCheck />, roles: ["INSTRUCTOR", "ADMIN"] },
  { href: "/admin", label: "Quản trị", icon: <IconShield />, roles: ["ADMIN"] },
  { href: "/courses", label: "Lớp học", icon: <IconCourses /> },
  { href: "/documents", label: "Tài liệu", icon: <IconDocuments />, roles: ["INSTRUCTOR", "ADMIN"] },
];

const ROLE_LABEL: Record<UserRole, string> = {
  STUDENT: "Sinh viên",
  INSTRUCTOR: "Giảng viên",
  ADMIN: "Quản trị viên",
};

export default function Sidebar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  if (!user) return null;

  const visibleItems = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(user.role));

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <aside
      className="sticky top-0 flex h-screen w-60 flex-shrink-0 flex-col"
      style={{ background: "var(--sidebar)", color: "var(--sidebar-ink)" }}
    >
      <div
        className="flex items-center gap-2.5 border-b px-[18px] py-[14px]"
        style={{ borderColor: "var(--sidebar-line)" }}
      >
        <div
          className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-lg"
          style={{ background: "var(--accent)" }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
          </svg>
        </div>
        <div>
          <div className="text-[13px] font-bold leading-tight text-white">Academic Assistant</div>
          <div className="text-[10.5px]" style={{ color: "#6b70a0" }}>
            {ROLE_LABEL[user.role]}
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-1.5">
        <div className="px-[18px] pb-1.5 pt-3.5 text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: "#545a8a" }}>
          Học tập
        </div>
        {visibleItems.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-2.5 border-l-[3px] px-[18px] py-2 text-[12.8px]"
              style={
                active
                  ? { background: "var(--sidebar-active)", borderLeftColor: "var(--accent)", color: "#fff", fontWeight: 600 }
                  : { borderLeftColor: "transparent" }
              }
            >
              <span className="inline-flex w-4 items-center justify-center opacity-80">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t px-[18px] py-3" style={{ borderColor: "var(--sidebar-line)" }}>
        <div className="mb-2 truncate text-[11px]" style={{ color: "var(--sidebar-ink)" }}>
          {user.full_name}
        </div>
        <button
          onClick={handleLogout}
          className="w-full rounded-lg border px-3 py-1.5 text-[11px] font-semibold hover:opacity-80"
          style={{ borderColor: "var(--sidebar-line)", color: "var(--sidebar-ink)" }}
        >
          Đăng xuất
        </button>
      </div>
    </aside>
  );
}
