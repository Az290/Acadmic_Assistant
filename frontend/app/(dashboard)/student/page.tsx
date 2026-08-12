"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, CoursePublic } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import WeakestConceptToast from "@/components/WeakestConceptToast";

/**
 * Trang chủ sinh viên - dạng "hub" điều hướng: 1 banner chào + các thẻ
 * lớn dẫn tới từng chức năng, thay vì nhồi mọi số liệu vào đây.
 *
 * Chi tiết tiến độ học tập nằm ở trang riêng /mastery - trang này chỉ
 * cần trả lời câu hỏi "hôm nay tôi làm gì tiếp theo?".
 *
 * Proactive Toast giữ NGUYÊN hành vi cũ (xem components/WeakestConceptToast.tsx),
 * không đổi gì khi bố cục trang thay đổi.
 */
export default function StudentDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [courses, setCourses] = useState<CoursePublic[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<CoursePublic[]>("/v1/courses/me")
      .then(setCourses)
      .catch(() => setCourses([]))
      .finally(() => setLoading(false));
  }, []);

  /**
   * Mở khung chat ở đúng tab mong muốn. Tái dùng CustomEvent đã có sẵn
   * cho Proactive Toast - ChatBubble nằm trong layout dùng chung nên
   * không truyền props trực tiếp được (xem components/ChatBubble.tsx).
   */
  function openChat(tab: "RAG_QUESTION" | "SOCRATIC_REQUEST") {
    window.dispatchEvent(new CustomEvent("open-chat-tab", { detail: { tab } }));
  }

  return (
    <div className="max-w-4xl">
      <WeakestConceptToast />

      <div
        className="rounded-[14px] px-6 py-6"
        style={{ background: "linear-gradient(135deg, #1A1440 0%, #0E1225 100%)" }}
      >
        <div className="text-[12px]" style={{ color: "#9B8FE0" }}>
          Xin chào, {user?.full_name ?? "bạn"}
        </div>
        <div className="mt-1.5 font-mono text-[34px] font-extrabold leading-tight text-white">
          Hôm nay học gì?
        </div>
        <div className="mt-2 text-[13px] leading-relaxed" style={{ color: "#B3ACD4" }}>
          {loading
            ? "Đang tải lớp học của bạn…"
            : courses.length > 0
              ? `Bạn đang theo học ${courses.length} lớp. Trợ lý AI sẵn sàng hỗ trợ bạn bất cứ lúc nào.`
              : "Bạn chưa thuộc lớp nào — liên hệ giảng viên để được thêm vào lớp."}
        </div>
      </div>

      <div className="mt-4 space-y-2.5">
        <HubCard
          title="Hỏi đáp học thuật"
          description="Đặt câu hỏi bất kỳ — AI trả lời dựa trên tài liệu đã được giảng viên duyệt, kèm trích dẫn nguồn để bạn tự kiểm chứng."
          onClick={() => openChat("RAG_QUESTION")}
        />
        <HubCard
          title="Gia sư AI"
          description="Học theo phương pháp Socratic — AI gợi mở để bạn tự tìm ra đáp án thay vì đưa lời giải ngay."
          onClick={() => openChat("SOCRATIC_REQUEST")}
        />
        <HubCard
          title="Tiến độ học tập"
          description="Xem bạn đã nắm vững phần nào, phần nào cần ôn lại, và làm quiz ôn tập."
          onClick={() => router.push("/mastery")}
        />
        <HubCard
          title="Lịch sử hỏi đáp"
          description="Xem lại toàn bộ câu hỏi bạn đã đặt và nguồn tài liệu AI đã dùng để trả lời."
          onClick={() => router.push("/history")}
        />
      </div>
    </div>
  );
}

function HubCard({
  title,
  description,
  onClick,
}: {
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="block w-full rounded-[12px] border px-4 py-4 text-left transition-colors hover:border-[color:var(--accent)]"
      style={{ background: "#fff", borderColor: "var(--border-strong)" }}
    >
      <div className="text-[15px] font-bold">{title}</div>
      <div className="mt-1 text-[12.5px] leading-relaxed" style={{ color: "var(--ink-soft)" }}>
        {description}
      </div>
    </button>
  );
}
