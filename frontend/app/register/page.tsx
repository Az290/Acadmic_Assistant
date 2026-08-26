"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import Image from "next/image";

export default function RegisterPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // Đăng ký công khai LUÔN tạo role STUDENT - backend không cho
      // chọn role khác (xem app/auth/router.py) - đây không phải giới
      // hạn Frontend, giáo viên do ADMIN tạo riêng.
      await api.post("/v1/auth/register", { email, password, full_name: fullName });
      // register() không tự đăng nhập - gọi login() ngay sau để trải
      // nghiệm liền mạch, không bắt user gõ lại thông tin lần 2.
      await api.post("/v1/auth/login", { email, password });
      await refreshUser();
      // Đăng ký công khai luôn là STUDENT (backend ép), nên đích đến
      // chắc chắn là dashboard sinh viên.
      router.push("/student");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Không thể đăng ký, vui lòng thử lại.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-showcase">
        <div className="auth-showcase__content">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-[#58779a]">Academic Assistant</p>
        <h1 className="auth-heading mt-12 max-w-xl text-[34px] font-bold leading-tight tracking-[-0.035em] text-[#132f50]">Bắt đầu hành trình học tập của bạn</h1>
        <p className="auth-lead mt-4 max-w-xl text-[14px] leading-7 text-[#58708b]">Tham gia lớp học, khám phá tài liệu đã kiểm duyệt và nhận hướng dẫn riêng từ Nova.</p>
        <div className="auth-feature"><span className="auth-feature__icon">✓</span><div><h2 className="font-semibold text-[#183b62]">Nguồn học liệu tin cậy</h2><p className="mt-1 text-sm leading-6 text-[#657b92]">Câu trả lời có trích dẫn từ tài liệu đã được giảng viên duyệt.</p></div></div>
        <div className="auth-feature"><span className="auth-feature__icon">✦</span><div><h2 className="font-semibold text-[#183b62]">Gia sư luôn sẵn sàng</h2><p className="mt-1 text-sm leading-6 text-[#657b92]">Nova gợi mở từng bước để bạn thực sự hiểu bài.</p></div></div>
        <div className="auth-feature"><span className="auth-feature__icon">↗</span><div><h2 className="font-semibold text-[#183b62]">Lộ trình phù hợp</h2><p className="mt-1 text-sm leading-6 text-[#657b92]">Biết phần nào đã vững và chủ động ôn lại đúng phần còn yếu.</p></div></div>
        <div className="auth-proof" aria-label="Điểm nổi bật của hệ thống">
          <div><strong>Một nơi</strong><span>Lớp, bài tập, tài liệu</span></div>
          <div><strong>Rõ nguồn</strong><span>Trích dẫn kiểm chứng</span></div>
          <div><strong>Đúng lúc</strong><span>Gợi ý học tiếp</span></div>
        </div>
        </div>
      </section>
      <section className="auth-stage">
      <div className="auth-card">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[.14em] text-[#6684a5]">Tài khoản sinh viên</p>
        <h1 className="mb-1 text-2xl font-bold tracking-[-.025em] text-slate-900">Đăng ký</h1>
        <p className="mb-6 text-sm text-slate-500">Tạo tài khoản sinh viên mới</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Họ và tên</label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="Nguyễn Văn A"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="ban@truong.edu.vn"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Mật khẩu</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="Tối thiểu 8 ký tự"
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
            {submitting ? "Đang đăng ký…" : "Đăng ký"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-slate-500">
          Đã có tài khoản?{" "}
          <Link href="/login" className="font-medium text-indigo-600 hover:underline">
            Đăng nhập
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
