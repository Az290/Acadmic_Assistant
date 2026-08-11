"use client";

import { useEffect, useState } from "react";
import { api, ApiError, ProfileStats } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

const ROLE_LABEL: Record<string, string> = {
  STUDENT: "Sinh viên",
  INSTRUCTOR: "Giảng viên",
  ADMIN: "Quản trị viên",
};

/**
 * Hồ sơ cá nhân - thông tin tài khoản (đã có sẵn từ AuthContext, không
 * gọi thêm API) + thống kê sử dụng của CHÍNH người dùng (gọi
 * /v1/profile/stats). Không hiển thị dữ liệu của người khác.
 */
export default function ProfilePage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<ProfileStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<ProfileStats>("/v1/profile/stats")
      .then(setStats)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Không tải được thống kê sử dụng."))
      .finally(() => setLoading(false));
  }, []);

  if (!user) return null;

  return (
    <div className="max-w-3xl">
      <div className="grid grid-cols-2 gap-3">
        <div className="card">
          <h3 className="mb-2 text-[12.5px] font-bold">Thông tin cá nhân</h3>
          <KvRow k="Họ tên" v={user.full_name} />
          <KvRow k="Email" v={user.email} />
          <KvRow
            k="Vai trò"
            v={
              <span
                className="rounded-full px-2.5 py-[3px] text-[10.5px] font-bold"
                style={{ background: "var(--accent-bg)", color: "var(--accent-ink)" }}
              >
                {ROLE_LABEL[user.role] ?? user.role}
              </span>
            }
          />
        </div>

        <div className="card">
          <h3 className="mb-2 text-[12.5px] font-bold">Thống kê sử dụng</h3>
          {loading && (
            <p className="text-[12.5px]" style={{ color: "var(--ink-faint)" }}>
              Đang tải…
            </p>
          )}
          {error && (
            <p className="text-[12.5px]" style={{ color: "var(--red-ink)" }}>
              {error}
            </p>
          )}
          {stats && (
            <>
              <KvRow k="Tổng câu hỏi" v={String(stats.total_questions)} />
              <KvRow k="Câu hỏi tuần này" v={String(stats.questions_this_week)} />
              <KvRow k="Quiz đã làm" v={String(stats.quizzes_taken)} />
              <KvRow
                k="Mastery trung bình"
                v={stats.avg_mastery !== null ? `${(stats.avg_mastery * 100).toFixed(0)}%` : "Chưa có dữ liệu"}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function KvRow({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b py-1.5 text-[12.5px] last:border-0" style={{ borderColor: "var(--border)" }}>
      <span style={{ color: "var(--ink-soft)" }}>{k}</span>
      <span className="font-mono font-semibold">{v}</span>
    </div>
  );
}
