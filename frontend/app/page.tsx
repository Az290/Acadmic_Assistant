"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";

/**
 * Trang gốc "/" chỉ đóng vai trò ĐIỀU HƯỚNG - đưa người dùng tới đúng
 * chỗ tuỳ đã đăng nhập hay chưa, không tự hiển thị nội dung gì.
 */
export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/courses" : "/login");
  }, [loading, user, router]);

  return (
    <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
      Đang tải…
    </div>
  );
}
