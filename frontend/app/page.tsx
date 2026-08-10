"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { dashboardPathForRole } from "@/lib/api";

/**
 * Trang gốc "/" chỉ đóng vai trò ĐIỀU HƯỚNG - đưa người dùng tới đúng
 * dashboard theo VAI TRÒ (mỗi role 1 giao diện riêng), hoặc màn hình
 * đăng nhập nếu chưa đăng nhập. Không tự hiển thị nội dung gì.
 */
export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? dashboardPathForRole(user.role) : "/login");
  }, [loading, user, router]);

  return (
    <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
      Đang tải…
    </div>
  );
}
