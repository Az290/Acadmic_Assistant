/**
 * Avatar của Nova - trợ lý học thuật.
 *
 * Hình ngôi sao 4 cánh: "nova" trong thiên văn là ngôi sao bừng sáng.
 * Nét mảnh, hình học thuần - gợi tri thức và khám phá mà KHÔNG nhân
 * cách hoá thành con người (tránh chân dung "nhà bác học" vừa sáo mòn
 * vừa dễ trông kỳ quặc ở kích thước nhỏ).
 *
 * Vẽ bằng SVG thay vì dùng file ảnh: sắc nét ở mọi kích thước và độ
 * phân giải màn hình, đổi màu theo ngữ cảnh được, không tốn thêm 1
 * lượt tải mạng.
 */
export default function NovaAvatar({ size = 28 }: { size?: number }) {
  return (
    <span
      className="inline-flex flex-shrink-0 items-center justify-center rounded-full"
      style={{ width: size, height: size, background: "var(--accent)" }}
      aria-hidden="true"
    >
      <svg
        width={size * 0.55}
        height={size * 0.55}
        viewBox="0 0 24 24"
        fill="none"
        stroke="#fff"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* 4 cánh cong vào tâm - đường cong (Q) thay vì đường thẳng để
            hình mềm mại hơn, không sắc nhọn như ngôi sao cảnh báo. */}
        <path d="M12 2.5 Q13 9.5 21.5 12 Q13 14.5 12 21.5 Q11 14.5 2.5 12 Q11 9.5 12 2.5 Z" />
      </svg>
    </span>
  );
}
