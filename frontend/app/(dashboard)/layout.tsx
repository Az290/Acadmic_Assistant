"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import ChatBubble from "@/components/ChatBubble";

/**
 * Layout dùng chung cho MỌI trang cần đăng nhập (Courses, Documents...)
 * - route group (dashboard) không xuất hiện trong URL.
 *
 * ChatBubble đặt Ở ĐÂY (ngoài <main>, cùng cấp Sidebar) để nổi trên
 * MỌI trang con - không có trang /chat riêng nữa, đúng thiết kế
 * prototype (chat là 1 panel nổi luôn sẵn sàng, không phải điều hướng
 * sang trang khác).
 *
 * Redirect về /login nếu chưa đăng nhập LÀ LỚP UX, KHÔNG PHẢI LỚP BẢO
 * MẬT - backend vẫn tự kiểm tra quyền ở mọi endpoint dù Frontend có
 * chặn hay không (đúng nguyên tắc "không tin tưởng phía client" đã
 * áp dụng xuyên suốt dự án). Việc redirect ở đây chỉ để trải nghiệm
 * mượt hơn, không phải hàng rào bảo vệ thật.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Đang tải…
      </div>
    );
  }

  if (!user) return null; // đợi useEffect redirect, tránh chớp nội dung trước khi chuyển trang

  return (
    <div className="dashboard-shell flex min-h-screen" style={{ background: "var(--bg)" }}>
      <Sidebar />
      <div className="dashboard-stage flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="dashboard-content flex-1 overflow-y-auto px-7 py-[22px]">
          <div className="dashboard-content__inner">{children}</div>
        </main>
      </div>
      <ChatBubble />
    </div>
  );
}
