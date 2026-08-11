"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, MasteryOverview } from "@/lib/api";

function levelColor(mastery: number): string {
  if (mastery < 0.4) return "var(--red)";
  if (mastery < 0.7) return "var(--amber)";
  return "var(--teal)";
}

const LEVEL_BADGE_STYLE: Record<"LOW" | "MID", React.CSSProperties> = {
  LOW: { background: "var(--red-bg)", color: "var(--red-ink)" },
  MID: { background: "var(--amber-bg)", color: "var(--amber-ink)" },
};

/**
 * Tiến độ học tập đầy đủ - tổng quan mọi course đã enroll, KHÁC
 * Proactive Toast (banner tạm 1 khái niệm) và /student (trang chủ gọn).
 * Cả 2 dùng chung app/learning/mastery_overview.py::compute_weak_concepts()
 * ở backend nhưng response khác nhau (Toast = 1 kết quả, trang này = danh sách).
 */
export default function MasteryPage() {
  const [data, setData] = useState<MasteryOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<MasteryOverview>("/v1/learn/mastery/overview")
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Không tải được tiến độ học tập."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
        Đang tải…
      </p>
    );
  }

  if (error) {
    return (
      <p className="rounded-[9px] px-3 py-2 text-[13px]" style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}>
        {error}
      </p>
    );
  }

  if (!data || data.overall_mastery === null) {
    return (
      <div className="card max-w-3xl">
        <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
          Bạn chưa làm quiz nào - hãy hỏi bài qua chat để hệ thống bắt đầu theo dõi tiến độ.
        </p>
      </div>
    );
  }

  const overallPct = Math.round(data.overall_mastery * 100);

  return (
    <div className="max-w-3xl">
      <p className="mb-4 rounded-[9px] px-3 py-2 text-[12.5px]" style={{ background: "var(--teal-bg)", color: "var(--teal-ink)" }}>
        Hệ thống theo dõi mức độ hiểu bài của bạn qua các lần hỏi đáp và làm quiz. Phần nào yếu sẽ được gợi ý ôn lại.
      </p>

      <div className="grid grid-cols-3 gap-3">
        {/* Vòng tròn tổng thể - conic-gradient thuần CSS, không cần thư viện chart */}
        <div className="card flex flex-col items-center justify-center text-center">
          <div
            className="flex h-24 w-24 items-center justify-center rounded-full font-mono text-xl font-extrabold"
            style={{
              background: `conic-gradient(${levelColor(data.overall_mastery)} ${overallPct * 3.6}deg, #E8EAF0 0deg)`,
            }}
          >
            <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-white">
              {overallPct}%
            </div>
          </div>
          <h3 className="mt-2.5 text-[12.5px] font-bold">Tổng thể</h3>
          <p className="text-[11.5px]" style={{ color: "var(--ink-faint)" }}>
            Trung bình tất cả môn
          </p>
        </div>

        {/* Theo môn */}
        <div className="card">
          <h3 className="mb-2 text-[12.5px] font-bold">Theo môn học</h3>
          {data.by_course.map((c) => {
            const pct = Math.round(c.avg_mastery * 100);
            return (
              <div key={c.course_id} className="mb-2.5 last:mb-0">
                <div className="flex items-center justify-between text-[12.5px]">
                  <span>{c.course_code}</span>
                  <span
                    className="rounded-full px-2 py-[2px] text-[10.5px] font-bold"
                    style={{ background: "#E8EAF0", color: levelColor(c.avg_mastery) }}
                  >
                    {pct}%
                  </span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-[4px]" style={{ background: "#E8EAF0" }}>
                  <div className="h-full rounded-[4px]" style={{ width: `${pct}%`, background: levelColor(c.avg_mastery) }} />
                </div>
              </div>
            );
          })}
        </div>

        {/* Gợi ý ôn tập */}
        <div className="card">
          <h3 className="mb-2 text-[12.5px] font-bold">Gợi ý ôn tập</h3>
          {data.weak_concepts.length === 0 && (
            <p className="text-[12px]" style={{ color: "var(--ink-faint)" }}>
              Không có khái niệm nào cần ôn lại - làm tốt lắm!
            </p>
          )}
          {data.weak_concepts.map((w) => (
            <div key={w.concept_id} className="mb-2 flex items-center gap-2 last:mb-0">
              <span
                className="flex h-6 w-8 shrink-0 items-center justify-center rounded-[6px] text-[9.5px] font-bold"
                style={LEVEL_BADGE_STYLE[w.level]}
              >
                {w.level}
              </span>
              <div className="min-w-0">
                <div className="truncate text-[12px] font-semibold">{w.concept_name}</div>
                <div className="text-[10.5px]" style={{ color: "var(--ink-soft)" }}>
                  {w.course_code} · Mastery: {Math.round(w.accuracy * 100)}%
                </div>
              </div>
            </div>
          ))}
          {data.weak_concepts.length > 0 && (
            <Link
              href={`/quiz?concept_id=${data.weak_concepts[0].concept_id}`}
              className="mt-2 block rounded-[7px] px-3 py-1.5 text-center text-[12.3px] font-semibold text-white"
              style={{ background: "var(--accent)" }}
            >
              Làm quiz ôn tập
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
