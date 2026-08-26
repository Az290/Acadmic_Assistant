"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { UserRole } from "@/lib/api";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  // Nhóm hiển thị trong sidebar - gom mục theo CÔNG VIỆC người dùng
  // đang làm, thay vì đổ tất cả vào 1 danh sách phẳng. Với giảng viên
  // (có 6-7 mục) danh sách phẳng khiến mắt phải quét lại từ đầu mỗi lần.
  group: "Học tập" | "Giảng dạy" | "Hệ thống" | "Tài khoản";
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

function IconUser() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function IconHistory() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function IconTrend() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

// Mỗi role vào ĐÚNG dashboard của mình (yêu cầu đã chốt từ Tác vụ #3):
// trang chủ khác nhau hoàn toàn theo vai trò, không phải 1 giao diện
// chung có nút chuyển role.
const NAV_ITEMS: NavItem[] = [
  // Học tập - việc sinh viên làm hằng ngày
  { href: "/student", label: "Trang chủ", icon: <IconHome />, roles: ["STUDENT"], group: "Học tập" },
  { href: "/mastery", label: "Tiến độ học tập", icon: <IconTrend />, roles: ["STUDENT"], group: "Học tập" },
  { href: "/assignments", label: "Bài tập", icon: <IconAssignment />, group: "Học tập" },
  { href: "/history", label: "Lịch sử hỏi đáp", icon: <IconHistory />, roles: ["STUDENT"], group: "Học tập" },
  { href: "/courses", label: "Lớp học", icon: <IconCourses />, group: "Học tập" },

  // Không giới hạn roles: sinh viên ĐANG HỌC lớp cũng được đóng góp
  // tài liệu (backend documents/router.py đã cho phép), không chỉ
  // giảng viên tải lên. Đặt ở nhóm "Học tập" (giống "Bài tập" ở trên,
  // cũng không giới hạn role) thay vì "Giảng dạy" - tránh sinh viên
  // thấy mục của mình lạc trong 1 nhóm mang tên dành cho giảng viên.
  { href: "/documents", label: "Tài liệu", icon: <IconDocuments />, group: "Học tập" },

  // Giảng dạy - việc giảng viên làm với lớp mình phụ trách
  { href: "/instructor", label: "Thống kê lớp", icon: <IconChart />, roles: ["INSTRUCTOR", "ADMIN"], group: "Giảng dạy" },
  { href: "/review", label: "Duyệt tài liệu", icon: <IconCheck />, roles: ["INSTRUCTOR", "ADMIN"], group: "Giảng dạy" },

  // Hệ thống - toàn hệ thống, không thuộc lớp nào
  { href: "/admin", label: "Quản trị", icon: <IconShield />, roles: ["ADMIN"], group: "Hệ thống" },

  { href: "/profile", label: "Hồ sơ cá nhân", icon: <IconUser />, group: "Tài khoản" },
];

const GROUP_ORDER = ["Học tập", "Giảng dạy", "Hệ thống", "Tài khoản"] as const;

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
      className="app-sidebar sticky top-0 flex h-screen w-60 flex-shrink-0 flex-col"
      style={{ background: "var(--sidebar)", color: "var(--sidebar-ink)" }}
    >
      <div className="sidebar-brand px-5 py-5">
        <div className="flex items-center gap-2.5">
          <span className="brand-mark" aria-hidden="true">A</span>
          <div>
        <div className="text-[13.5px] font-semibold leading-tight text-white">Academic Assistant</div>
        <div className="mt-0.5 text-[11px]" style={{ color: "var(--sidebar-ink)" }}>
          {ROLE_LABEL[user.role]}
        </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto pb-3">
        {GROUP_ORDER.map((group) => {
          const items = visibleItems.filter((i) => i.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group} className="mb-1">
              <div
                className="px-5 pb-1.5 pt-4 text-[10px] font-semibold uppercase tracking-[0.08em]"
                style={{ color: "#5b6b85" }}
              >
                {group}
              </div>
              {items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(item.href + "/");
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="sidebar-link relative flex items-center gap-2.5 px-5 py-[7px] text-[12.8px]"
                    style={{
                      color: active ? "#fff" : "var(--sidebar-ink)",
                      fontWeight: active ? 600 : 400,
                      background: active ? "var(--sidebar-active)" : "transparent",
                      transition: "color var(--motion-fast) var(--ease), background-color var(--motion-fast) var(--ease)",
                    }}
                  >
                    {/* Vạch dọc đánh dấu mục đang mở - đặt absolute để
                        không đẩy chữ lệch sang phải như khi dùng
                        border-left (mọi mục sẽ thẳng hàng dù đang ở
                        trạng thái nào). */}
                    {active && (
                      <span
                        className="absolute left-0 top-1/2 h-[18px] w-[2px] -translate-y-1/2 rounded-r"
                        style={{ background: "var(--accent-strong)" }}
                      />
                    )}
                    <span className="inline-flex w-4 items-center justify-center" style={{ opacity: active ? 1 : 0.65 }}>
                      {item.icon}
                    </span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="sidebar-account border-t px-5 py-4" style={{ borderColor: "var(--sidebar-line)" }}>
        <div className="mb-2.5 flex items-center gap-2.5">
          <span className="sidebar-user-avatar">{user.full_name.trim().slice(-1).toUpperCase()}</span>
          <div className="min-w-0">
            <div className="truncate text-[12px] font-semibold text-white">{user.full_name}</div>
            <div className="text-[10px]">{ROLE_LABEL[user.role]}</div>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="w-full rounded-[6px] border py-1.5 text-[11.5px] font-medium"
          style={{
            borderColor: "var(--sidebar-line)",
            color: "var(--sidebar-ink)",
            transition: "border-color var(--motion-fast) var(--ease), color var(--motion-fast) var(--ease)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "#3b4a63";
            e.currentTarget.style.color = "#fff";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--sidebar-line)";
            e.currentTarget.style.color = "var(--sidebar-ink)";
          }}
        >
          Đăng xuất
        </button>
      </div>
    </aside>
  );
}
