"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, dashboardPathForRole } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import Image from "next/image";

// Tài khoản demo CÔNG KHAI dùng cho khách/doanh nghiệp xem thử sản phẩm -
// không phải bí mật cần giấu, đã tạo sẵn trong DB để bấm-là-vào-luôn.
const DEMO_INSTRUCTOR = { email: "gv.demo@academic-assistant.vn", password: "Demo@2026" };
const DEMO_STUDENT = { email: "sv.demo@academic-assistant.vn", password: "Demo@2026" };

export default function LoginPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Logic đăng nhập dùng chung cho cả form thật lẫn 2 nút demo: gọi API,
  // rồi điều hướng theo ĐÚNG vai trò - mỗi role có dashboard riêng, không
  // dùng chung 1 trang đích cho mọi người.
  async function loginWith(loginEmail: string, loginPassword: string) {
    setError(null);
    setSubmitting(true);
    try {
      await api.post("/v1/auth/login", { email: loginEmail, password: loginPassword });
      const me = await refreshUser();
      router.push(me ? dashboardPathForRole(me.role) : "/student");
    } catch (err) {
      // Backend cố tình trả cùng 1 thông báo chung cho "sai email" lẫn
      // "sai mật khẩu" (chống dò email đã đăng ký) - hiển thị nguyên
      // văn, không tự diễn giải thêm.
      setError(err instanceof ApiError ? err.detail : "Không thể đăng nhập, vui lòng thử lại.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    void loginWith(email, password);
  }

  return (
    <div className="auth-shell">
      <section className="auth-showcase">
        <div className="auth-showcase__content">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[#58779a]">Academic Assistant</p>
        <h1 className="auth-heading mt-12 max-w-xl text-[34px] font-bold leading-tight tracking-[-0.035em] text-[#132f50]">
          Học thông minh hơn cùng Nova
        </h1>
        <p className="auth-lead mt-4 max-w-xl text-[14px] leading-7 text-[#58708b]">
          Một không gian học tập liền mạch, nơi tài liệu, tiến độ và trợ lý AI cùng đồng hành với bạn.
        </p>
        <div className="auth-feature">
          <span className="auth-feature__icon">⌂</span>
          <div><h2 className="font-semibold text-[#183b62]">Trung tâm học tập</h2><p className="mt-1 text-sm leading-6 text-[#657b92]">Mọi lớp học, bài tập và tài liệu được tổ chức rõ ràng tại một nơi.</p></div>
        </div>
        <div className="auth-feature">
          <span className="auth-feature__icon">↗</span>
          <div><h2 className="font-semibold text-[#183b62]">Tiến độ cá nhân</h2><p className="mt-1 text-sm leading-6 text-[#657b92]">Theo dõi mức độ nắm vững và nhận gợi ý ôn tập phù hợp.</p></div>
        </div>
        <div className="auth-feature">
          <span className="auth-feature__icon">✦</span>
          <div><h2 className="font-semibold text-[#183b62]">Nova đồng hành</h2><p className="mt-1 text-sm leading-6 text-[#657b92]">Hỏi đáp có trích dẫn hoặc học theo phương pháp gợi mở Socratic.</p></div>
        </div>
        <div className="auth-proof" aria-label="Điểm nổi bật của hệ thống">
          <div><strong>24/7</strong><span>Trợ lý học tập</span></div>
          <div><strong>100%</strong><span>Nguồn có kiểm duyệt</span></div>
          <div><strong>Riêng bạn</strong><span>Lộ trình thích ứng</span></div>
        </div>
        </div>
      </section>
      <section className="auth-stage">
      <div className="auth-card">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[.14em] text-[#6684a5]">Chào mừng trở lại</p>
        <h1 className="mb-1 text-2xl font-bold tracking-[-.025em] text-slate-900">Đăng nhập</h1>
        <p className="mb-6 text-sm text-slate-500">Academic Assistant</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:opacity-60"
              placeholder="ban@truong.edu.vn"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Mật khẩu</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:opacity-60"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn btn-primary w-full py-2.5 text-sm disabled:opacity-60"
          >
            {submitting ? "Đang đăng nhập…" : "Đăng nhập"}
          </button>
        </form>

        <div className="mt-6">
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white px-2 text-slate-400">Hoặc dùng tài khoản demo</span>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <button
              type="button"
              disabled={submitting}
              onClick={() => void loginWith(DEMO_INSTRUCTOR.email, DEMO_INSTRUCTOR.password)}
              className="card-interactive w-full !p-3 text-sm font-semibold text-[#285f9f] disabled:opacity-60"
            >
              🎓 Giảng viên
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => void loginWith(DEMO_STUDENT.email, DEMO_STUDENT.password)}
              className="card-interactive w-full !p-3 text-sm font-semibold text-[#285f9f] disabled:opacity-60"
            >
              📚 Sinh viên
            </button>
          </div>
        </div>

        <p className="mt-4 text-center text-sm text-slate-500">
          Chưa có tài khoản?{" "}
          <Link href="/register" className="font-medium text-indigo-600 hover:underline">
            Đăng ký
          </Link>
        </p>
      </div>
      <div className="auth-nova" aria-hidden="true">
        <Image src="/nova-mascot.png" alt="" width={300} height={300} priority />
      </div>
      </section>
    </div>
  );
}
