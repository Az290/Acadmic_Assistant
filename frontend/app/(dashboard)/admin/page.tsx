"use client";

import Link from "next/link";

/**
 * Dashboard quản trị viên.
 *
 * Eval Dashboard (đo chất lượng hệ thống qua scripts/eval.py) đã có
 * trang riêng ở /admin/eval - xem file app/(dashboard)/admin/eval/page.tsx.
 * Các chức năng quản trị khác (quản lý tài khoản người dùng, cấu hình
 * hệ thống) chưa được xây dựng ở giai đoạn này.
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
            href="/admin/eval"
            className="rounded-[7px] px-3 py-1.5 text-[12.3px] font-semibold text-white"
            style={{ background: "var(--teal)" }}
          >
            Eval Dashboard
          </Link>
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
          Quản lý tài khoản người dùng và cấu hình hệ thống chưa được xây dựng ở giai đoạn này.
        </p>
      </div>
    </div>
  );
}
