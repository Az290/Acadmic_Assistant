"use client";

import { useEffect, useState } from "react";
import { api, ApiError, EvalCaseResultPublic, EvalRunDetail, EvalRunSummary } from "@/lib/api";

/**
 * Eval Dashboard - lịch sử các lượt chạy scripts/eval.py, để phát hiện
 * SỚM khi 1 thay đổi code làm giảm chất lượng (Router category accuracy,
 * Retrieval Recall@K, LLM-judge score) thay vì chỉ biết được lúc người
 * dùng thật phàn nàn.
 *
 * KHÔNG có nút "chạy eval" ở đây - scripts/eval.py chạy TỪ MÁY DEV
 * (cần OPENAI_API_KEY và quyền truy cập trực tiếp DB để ghi kết quả),
 * trang này CHỈ ĐỌC lịch sử đã ghi.
 */
export default function EvalDashboardPage() {
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [detail, setDetail] = useState<EvalRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    api
      .get<EvalRunSummary[]>("/v1/eval-dashboard/runs")
      .then((list) => {
        setRuns(list);
        if (list.length > 0) setSelectedRunId(list[0].id);
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Không tải được lịch sử eval."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedRunId === null) return;
    setDetailLoading(true);
    api
      .get<EvalRunDetail>(`/v1/eval-dashboard/runs/${selectedRunId}`)
      .then(setDetail)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Không tải được chi tiết lượt eval."))
      .finally(() => setDetailLoading(false));
  }, [selectedRunId]);

  const latest = runs[0];
  const previous = runs[1];

  return (
    <div className="max-w-5xl">
      <p className="mb-4 text-[13px]" style={{ color: "var(--ink-soft)" }}>
        Lịch sử các lượt chạy <code>scripts/eval.py</code> (bộ câu hỏi mẫu cố định) - dùng để phát
        hiện sớm khi 1 thay đổi code làm giảm chất lượng hệ thống.
      </p>

      {error && (
        <p className="mb-3 rounded-[9px] px-3 py-2 text-[13px]" style={{ background: "var(--red-bg)", color: "var(--red-ink)" }}>
          {error}
        </p>
      )}

      {loading && (
        <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
          Đang tải…
        </p>
      )}

      {!loading && runs.length === 0 && !error && (
        <div className="card">
          <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
            Chưa có lượt eval nào. Chạy <code>python scripts/eval.py</code> từ máy dev (cần backend
            đang chạy) để tạo lượt đầu tiên.
          </p>
        </div>
      )}

      {latest && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          <SummaryCard
            label="Router category accuracy"
            value={`${(latest.category_accuracy * 100).toFixed(1)}%`}
            delta={previous ? latest.category_accuracy - previous.category_accuracy : null}
          />
          <SummaryCard
            label="Retrieval avg Recall@K"
            value={latest.avg_recall_at_k !== null ? `${(latest.avg_recall_at_k * 100).toFixed(1)}%` : "—"}
            delta={
              previous && latest.avg_recall_at_k !== null && previous.avg_recall_at_k !== null
                ? latest.avg_recall_at_k - previous.avg_recall_at_k
                : null
            }
          />
          <SummaryCard
            label="LLM-judge avg score"
            value={latest.avg_judge_score !== null ? latest.avg_judge_score.toFixed(2) : "—"}
            suffix="/5"
            delta={
              previous && latest.avg_judge_score !== null && previous.avg_judge_score !== null
                ? latest.avg_judge_score - previous.avg_judge_score
                : null
            }
            deltaScale={5}
          />
        </div>
      )}

      {runs.length > 0 && (
        <div className="grid grid-cols-[280px_1fr] gap-4">
          <div className="card !p-0">
            <div className="border-b px-3 py-2 text-[11.5px] font-bold" style={{ borderColor: "var(--border)" }}>
              Lịch sử ({runs.length} lượt)
            </div>
            <div className="max-h-[560px] overflow-y-auto">
              {runs.map((r) => {
                const active = r.id === selectedRunId;
                return (
                  <button
                    key={r.id}
                    onClick={() => setSelectedRunId(r.id)}
                    className="block w-full border-b px-3 py-2 text-left text-[12px]"
                    style={{
                      borderColor: "var(--border)",
                      background: active ? "var(--amber-bg)" : "transparent",
                    }}
                  >
                    <div className="font-semibold">
                      #{r.id} · {new Date(r.created_at).toLocaleString("vi-VN")}
                    </div>
                    <div className="mt-0.5" style={{ color: "var(--ink-soft)" }}>
                      {(r.category_accuracy * 100).toFixed(0)}% ·{" "}
                      {r.avg_judge_score !== null ? r.avg_judge_score.toFixed(2) : "—"}/5 ·{" "}
                      {r.git_commit_hash ? r.git_commit_hash.slice(0, 7) : "no-git"}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            {detailLoading && (
              <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
                Đang tải chi tiết…
              </p>
            )}
            {!detailLoading && detail && <RunDetailView detail={detail} />}
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  suffix,
  delta,
  deltaScale = 1,
}: {
  label: string;
  value: string;
  suffix?: string;
  delta: number | null;
  deltaScale?: number;
}) {
  return (
    <div className="card">
      <div className="text-[11px] font-semibold" style={{ color: "var(--ink-faint)" }}>
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold">
        {value}
        {suffix && <span className="text-sm font-medium" style={{ color: "var(--ink-faint)" }}> {suffix}</span>}
      </div>
      {delta !== null && Math.abs(delta) > 0.0005 && (
        <div
          className="mt-1 text-[11.5px] font-semibold"
          style={{ color: delta > 0 ? "var(--teal-ink, #0F7A5C)" : "var(--red-ink)" }}
        >
          {delta > 0 ? "▲" : "▼"} {deltaScale === 5 ? Math.abs(delta).toFixed(2) : `${(Math.abs(delta) * 100).toFixed(1)}%`} so
          với lượt trước
        </div>
      )}
    </div>
  );
}

function RunDetailView({ detail }: { detail: EvalRunDetail }) {
  return (
    <div className="card !p-0">
      <div className="border-b px-3 py-2.5 text-[12px]" style={{ borderColor: "var(--border)" }}>
        <div className="flex flex-wrap gap-x-4 gap-y-1" style={{ color: "var(--ink-soft)" }}>
          <span>
            <strong>Commit:</strong> {detail.git_commit_hash ? detail.git_commit_hash.slice(0, 12) : "không xác định"}
          </span>
          <span>
            <strong>Model:</strong> {detail.model_version}
          </span>
          <span>
            <strong>Dataset:</strong> {detail.dataset_version}
          </span>
          <span>
            <strong>Tổng số câu:</strong> {detail.total_cases} (lỗi: {detail.errors})
          </span>
        </div>
      </div>
      <div className="max-h-[500px] overflow-y-auto">
        {detail.cases.map((c) => (
          <CaseRow key={c.id} c={c} />
        ))}
      </div>
    </div>
  );
}

function CaseRow({ c }: { c: EvalCaseResultPublic }) {
  const ok = c.error === null && c.category_match !== false;
  return (
    <div className="border-b px-3 py-2.5 text-[12px]" style={{ borderColor: "var(--border)" }}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">{c.case_id}</span>
        <div className="flex items-center gap-2 text-[11px]" style={{ color: "var(--ink-faint)" }}>
          {c.judge_score !== null && <span>Judge: {c.judge_score}/5</span>}
          {c.recall_at_k !== null && <span>Recall: {(c.recall_at_k * 100).toFixed(0)}%</span>}
          <span
            className="rounded-full px-2 py-[2px] font-bold"
            style={
              ok
                ? { background: "var(--teal-bg, #DCF3EC)", color: "var(--teal-ink, #0F7A5C)" }
                : { background: "var(--red-bg)", color: "var(--red-ink)" }
            }
          >
            {c.error ? "Lỗi" : c.category_match ? "OK" : "Sai category"}
          </span>
        </div>
      </div>
      {c.error && (
        <p className="mt-1" style={{ color: "var(--red-ink)" }}>
          {c.error}
        </p>
      )}
      {c.judge_reasoning && (
        <p className="mt-1" style={{ color: "var(--ink-soft)" }}>
          {c.judge_reasoning}
        </p>
      )}
      {c.answer_preview && (
        <p className="mt-1 italic" style={{ color: "var(--ink-faint)" }}>
          "{c.answer_preview}"
        </p>
      )}
    </div>
  );
}
