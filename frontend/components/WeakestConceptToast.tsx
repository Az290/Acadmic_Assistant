"use client";

import { useEffect, useState } from "react";
import { api, ApiError, openTutorChat, WeakestConceptPublic } from "@/lib/api";

/**
 * Proactive AI Toast - chủ động gợi ý sinh viên hỏi gia sư về khái
 * niệm họ đang yếu nhất (accuracy < 50%, chưa mastered) thay vì đợi
 * sinh viên tự nhận ra và tự đi hỏi.
 *
 * Đặt ở /student và /assignments (nơi sinh viên bắt đầu phiên học) -
 * KHÔNG đặt trong DashboardLayout dùng chung như ChatBubble, vì Toast
 * chỉ nên xuất hiện ở các trang "bắt đầu phiên", không phải mọi trang
 * (tránh làm phiền khi đang xem tài liệu/thống kê).
 *
 * TỐI ĐA 1 LẦN/PHIÊN TRÌNH DUYỆT: dùng sessionStorage (không cần bảng
 * DB mới, không cần đồng bộ nhiều thiết bị) - đủ để tránh làm phiền
 * lặp lại mỗi lần chuyển trang trong cùng 1 phiên, nhưng vẫn nhắc lại
 * ở phiên MỚI (đóng tab, mở lại) nếu sinh viên vẫn chưa cải thiện.
 */
const SESSION_KEY = "weakest_concept_toast_shown";

export default function WeakestConceptToast() {
  const [weakest, setWeakest] = useState<WeakestConceptPublic | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (sessionStorage.getItem(SESSION_KEY) === "1") return;

    api
      .get<WeakestConceptPublic | null>("/v1/learn/weakest-concept")
      .then((result) => {
        if (result) {
          setWeakest(result);
          sessionStorage.setItem(SESSION_KEY, "1");
        }
      })
      .catch((err) => {
        // Lỗi tải gợi ý KHÔNG được làm phiền sinh viên bằng thông báo
        // lỗi - đây là tính năng chủ động, không phải yêu cầu chính họ
        // thực hiện. Im lặng bỏ qua, ghi console để debug nếu cần.
        if (err instanceof ApiError) console.warn("Không tải được gợi ý khái niệm yếu nhất:", err.detail);
      });
  }, []);

  if (!weakest || dismissed) return null;

  return (
    <div
      className="mb-4 flex items-start gap-3 rounded-[10px] border px-4 py-3"
      style={{ background: "var(--amber-bg)", borderColor: "#F0D589" }}
    >
      <span className="mt-0.5 text-lg">💡</span>
      <div className="min-w-0 flex-1">
        <p className="text-[12.8px] font-semibold" style={{ color: "var(--amber-ink)" }}>
          Có vẻ bạn đang gặp khó với "{weakest.concept_name}"
        </p>
        <p className="mt-0.5 text-[12px]" style={{ color: "var(--amber-ink)" }}>
          Bạn trả lời đúng {weakest.n_correct}/{weakest.n_obs} câu quiz về khái niệm này (
          {(weakest.accuracy * 100).toFixed(0)}%). Thử hỏi Gia sư để được gợi mở lại nhé.
        </p>
        <div className="mt-2 flex gap-2">
          <button
            onClick={() => {
              openTutorChat(weakest.course_id, weakest.concept_id);
              setDismissed(true);
            }}
            className="rounded-[7px] px-3 py-1.5 text-[12px] font-semibold text-white"
            style={{ background: "var(--accent)" }}
          >
            Hỏi gia sư
          </button>
          <button
            onClick={() => setDismissed(true)}
            className="rounded-[7px] border px-3 py-1.5 text-[12px] font-semibold"
            style={{ borderColor: "#E3C363", color: "var(--amber-ink)" }}
          >
            Để sau
          </button>
        </div>
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="text-sm font-bold opacity-60 hover:opacity-100"
        style={{ color: "var(--amber-ink)" }}
        aria-label="Đóng"
      >
        ✕
      </button>
    </div>
  );
}
