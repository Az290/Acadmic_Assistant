"use client";

import Link from "next/link";

/**
 * Dashboard quản trị viên.
 *
 * TRẠNG THÁI THẬT: backend hiện CHƯA có endpoint quản trị riêng nào
 * (quản lý người dùng, cấu hình hệ thống, thống kê toàn hệ thống, chi
 * phí LLM...) - trang này KHÔNG hiển thị số liệu giả để tránh gây hiểu
 * lầm là tính năng đã có. ADMIN hiện dùng được mọi chức năng của giảng
 * viên (backend cho phép ADMIN bỏ qua kiểm tra chủ sở hữu lớp).
 */
export default function AdminDashboard() {
  return (
    <div className="max-w-3xl">
      <div className="card mb-3">
        <h3 className="mb-2 text-[12.5px] font-bold">Quyền của bạn</h3>
        <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--ink-soft)" }}>
          Với vai trò quản trị viên, bạn truy cập được mọi lớp học trong hệ thống (không giới hạn ở
          lớp mình sở hữu), bao gồm thống kê và quản lý tài liệu.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link
            href="/instructor"
            className="rounded-[7px] px-3 py-1.5 text-[12.3px] font-semibold text-white"
            style={{ background: "var(--accent)" }}
          >
            Xem thống kê lớp
          </Link>
          <Link
            href="/courses"
            className="rounded-[7px] border px-3 py-1.5 text-[12.3px] font-semibold"
            style={{ borderColor: "var(--border-strong)", color: "var(--ink)" }}
          >
            Quản lý lớp học
          </Link>
        </div>
      </div>

      <div className="card">
        <h3 className="mb-2 text-[12.5px] font-bold">Chức năng quản trị riêng</h3>
        <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--ink-soft)" }}>
          Các chức năng dành riêng cho quản trị viên (quản lý tài khoản người dùng, theo dõi chi phí
          LLM, cấu hình hệ thống, nhật ký bảo mật toàn hệ thống) chưa được xây dựng ở giai đoạn này.
        </p>
      </div>
    </div>
  );
}
