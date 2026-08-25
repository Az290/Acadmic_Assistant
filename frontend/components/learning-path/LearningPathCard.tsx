"use client";

import { useEffect, useState } from "react";
import { ApiError, LearningPathResponse, getLearningPath } from "@/lib/api";

/**
 * Props cho LearningPathCard
 */
export interface LearningPathCardProps {
  courseId: number;
  courseName?: string;
  onConceptClick?: (conceptId: number) => void;
}

/**
 * LearningPathCard - Hiển thị lộ trình học tập của sinh viên trong 1 course.
 *
 * UI:
 * - Header với tên course
 * - Box gợi ý học tiếp (recommendations)
 * - Legend giải thích các trạng thái
 * - Danh sách concepts với progress
 * - Layout grid/flex không cần SVG connectors
 */
export default function LearningPathCard({ courseId, courseName, onConceptClick }: LearningPathCardProps) {
  const [data, setData] = useState<LearningPathResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLearningPath(courseId)
      .then(setData)
      .catch((err) => {
        console.error("Failed to load learning path:", err);
        setError(err instanceof ApiError ? err.detail : "Không tải được lộ trình học tập.");
      })
      .finally(() => setLoading(false));
  }, [courseId]);

  if (loading) {
    return (
      <div className="card">
        <div className="animate-pulse">
          <div className="h-5 w-48 rounded bg-gray-200" />
          <div className="mt-4 space-y-2">
            <div className="h-20 rounded bg-gray-200" />
            <div className="h-20 rounded bg-gray-200" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <p className="text-[13px]" style={{ color: "var(--red-ink)" }}>
          {error}
        </p>
      </div>
    );
  }

  if (!data || data.concepts.length === 0) {
    return (
      <div className="card">
        <p className="text-[13px]" style={{ color: "var(--ink-faint)" }}>
          Chưa có khái niệm nào trong lộ trình học tập của môn này.
        </p>
      </div>
    );
  }

  const displayName = courseName || data.course_name;
  // Gợi ý chính hiển thị ở banner đầu trang. "start_here" PHẢI có mặt
  // ở đây: sinh viên chưa làm quiz nào chỉ nhận được loại gợi ý đó từ
  // backend - bỏ sót nó khiến banner trống đúng với người mới, nhóm
  // cần định hướng nhất. Thứ tự trong mảng phản ánh thứ tự ưu tiên.
  const primaryRecommendation = data.recommendations.find(
    (r) => r.type === "next_learn" || r.type === "continue" || r.type === "start_here"
  );

  return (
    <div className="card">
      {/* Header */}
      <div className="mb-4 flex items-center gap-2">
        <span className="text-[16px]">📚</span>
        <h3 className="text-[14px] font-semibold">Lộ trình học tập</h3>
        <span className="text-[12px]" style={{ color: "var(--ink-soft)" }}>
          — {displayName}
        </span>
      </div>

      {/* Recommendation Box */}
      {primaryRecommendation && (
        <div
          className="mb-4 rounded-[8px] p-3"
          style={{ background: "var(--accent-bg)", borderLeft: "3px solid var(--accent)" }}
        >
          <div className="flex items-start gap-2">
            <span className="mt-0.5 text-[14px]">🎯</span>
            <div className="min-w-0 flex-1">
              <p className="text-[12.5px] font-semibold" style={{ color: "var(--accent-strong)" }}>
                {primaryRecommendation.type === "start_here" ? "Bắt đầu với" : "Học tiếp"}: &ldquo;{primaryRecommendation.concept_name}&rdquo;
              </p>
              <p className="mt-0.5 text-[11.5px]" style={{ color: "var(--ink-soft)" }}>
                {primaryRecommendation.reason}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="mb-4 flex flex-wrap gap-3 text-[10.5px]">
        <LegendItem icon="✅" label={`Hoàn thành (>80%)`} color="var(--teal)" />
        <LegendItem icon="🔄" label={`Đang học (20-80%)`} color="var(--amber)" />
        <LegendItem icon="🔓" label={`Sẵn sàng`} color="var(--accent)" />
        <LegendItem icon="🔒" label={`Bị khóa`} color="var(--ink-faint)" />
      </div>

      {/* Concepts Grid */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {data.concepts.map((concept) => (
          <ConceptNode
            key={concept.id}
            concept={concept}
            onClick={() => onConceptClick?.(concept.id)}
          />
        ))}
      </div>

      {/* Additional Recommendations */}
      {data.recommendations.length > 1 && (
        <div className="mt-4 border-t pt-3" style={{ borderColor: "var(--border)" }}>
          <p className="mb-2 text-[11px] font-semibold" style={{ color: "var(--ink-soft)" }}>
            Các gợi ý khác:
          </p>
          <div className="flex flex-wrap gap-2">
            {data.recommendations.slice(1, 4).map((rec, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10.5px]"
                style={{
                  background: rec.type === "review" ? "var(--amber-bg)" : "var(--bg-raised)",
                  color: rec.type === "review" ? "var(--amber-ink)" : "var(--ink-soft)",
                }}
              >
                {rec.type === "review" ? "📝" : "📖"}
                {rec.concept_name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Một node đại diện cho 1 concept trong lộ trình
 */
function ConceptNode({
  concept,
  onClick,
}: {
  concept: LearningPathResponse["concepts"][0];
  onClick?: () => void;
}) {
  const statusStyles = getStatusStyles(concept.status);
  const masteryPct = concept.mastery !== null ? Math.round(concept.mastery * 100) : null;

  return (
    <button
      onClick={onClick}
      disabled={concept.status === "locked"}
      className={`w-full rounded-[8px] border p-3 text-left transition-all ${
        concept.status === "locked" ? "cursor-not-allowed opacity-60" : "hover:shadow-md"
      }`}
      style={{
        borderColor: statusStyles.borderColor,
        background: statusStyles.bgColor,
      }}
    >
      {/* Concept Name */}
      <div className="flex items-start justify-between gap-2">
        <span
          className="text-[12.5px] font-semibold"
          style={{ color: statusStyles.textColor }}
        >
          {concept.name}
        </span>
        <span className="text-[12px]">{statusStyles.icon}</span>
      </div>

      {/* Mastery */}
      {masteryPct !== null ? (
        <div className="mt-2">
          <div className="flex items-center justify-between text-[10px]" style={{ color: "var(--ink-soft)" }}>
            <span>Mastery</span>
            <span className="font-medium" style={{ color: statusStyles.textColor }}>
              {masteryPct}%
            </span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${masteryPct}%`,
                background: statusStyles.progressColor,
              }}
            />
          </div>
        </div>
      ) : (
        <p className="mt-2 text-[10px]" style={{ color: "var(--ink-faint)" }}>
          {concept.status === "locked" ? "Chờ hoàn thành prerequisites" : "Chưa học"}
        </p>
      )}

      {/* Complexity & Time */}
      <div className="mt-2 flex items-center justify-between text-[9.5px]" style={{ color: "var(--ink-faint)" }}>
        <span>Độ khó: {concept.complexity}/5</span>
        <span>~{concept.estimated_time_minutes} phút</span>
      </div>
    </button>
  );
}

/**
 * Legend item
 */
function LegendItem({ icon, label, color }: { icon: string; label: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span>{icon}</span>
      <span style={{ color }}>{label}</span>
    </span>
  );
}

/**
 * Get styles based on concept status
 */
function getStatusStyles(status: string): {
  icon: string;
  borderColor: string;
  bgColor: string;
  textColor: string;
  progressColor: string;
} {
  switch (status) {
    case "completed":
      return {
        icon: "✅",
        borderColor: "var(--teal)",
        bgColor: "var(--teal-bg)",
        textColor: "var(--teal)",
        progressColor: "var(--teal)",
      };
    case "in_progress":
      return {
        icon: "🔄",
        borderColor: "var(--amber)",
        bgColor: "var(--amber-bg)",
        textColor: "var(--amber)",
        progressColor: "var(--amber)",
      };
    case "available":
      return {
        icon: "🔓",
        borderColor: "var(--accent)",
        bgColor: "var(--accent-bg)",
        textColor: "var(--accent-strong)",
        progressColor: "var(--accent)",
      };
    case "locked":
      return {
        icon: "🔒",
        borderColor: "var(--border)",
        bgColor: "var(--bg-subtle)",
        textColor: "var(--ink-faint)",
        progressColor: "var(--border)",
      };
    case "not_started":
    default:
      return {
        icon: "📖",
        borderColor: "var(--border)",
        bgColor: "var(--bg-raised)",
        textColor: "var(--ink-soft)",
        progressColor: "var(--border)",
      };
  }
}
