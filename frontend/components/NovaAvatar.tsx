/**
 * Avatar của Nova - trợ lý học thuật.
 *
 * Robot tối giản kiểu màn hình/thiết bị (khung mặt bo góc + 2 thanh
 * LED, gợi robot trợ lý kiểu BB-8/EVE) - nhân cách hoá NHẸ để tạo cảm
 * giác đang giao tiếp với thứ "sống" mà vẫn nghiêm túc, không sa vào
 * chân dung "nhà bác học" sáo mòn hay linh vật trẻ con.
 *
 * `state` phản ánh ĐÚNG 3 bước xử lý thật trong pipeline agent
 * (checking/searching/generating - xem DisplayMessage.status trong
 * ChatBubble.tsx) + "idle" khi không gắn với tin nhắn nào đang xử lý.
 * Không bịa thêm trạng thái không có căn cứ trong luồng thật.
 *
 * Vẽ bằng SVG dựng tay (không icon library, không ảnh raster): sắc nét
 * ở mọi kích thước/độ phân giải màn hình, đổi màu theo theme được,
 * không tốn thêm 1 lượt tải mạng.
 *
 * Màu: nền + khung vẫn dùng var(--accent)/var(--accent-ink) hiện có -
 * KHÔNG đổi màu hệ thống. Thêm ĐÚNG 1 màu mới #7ce0ff ("đèn LED" của
 * Nova) cho viền + mắt - cố ý KHÔNG tái dùng --teal/--blue vì đó là
 * màu semantic (thành công/thông tin) ở nơi khác trong app, tái dùng
 * sẽ làm loãng ý nghĩa gốc của chúng.
 *
 * Ăng-ten chỉ vẽ khi size >= 28 (loại hẳn khỏi DOM ở size nhỏ, không
 * phải ẩn bằng CSS) - ở 16-22px 2 chấm+cuống nhỏ dễ vỡ nét/dính thành
 * vệt mờ, bỏ hẳn để giữ khuôn mặt sạch thay vì cố nhét cho đủ chi tiết.
 */

export type NovaState = "idle" | "checking" | "searching" | "generating";

export default function NovaAvatar({
  size = 28,
  state = "idle",
}: {
  size?: number;
  state?: NovaState;
}) {
  const showAntenna = size >= 28;

  return (
    <span
      className={`nova-avatar nova-avatar--${state}`}
      style={{ width: size, height: size, background: "var(--accent)" }}
      aria-hidden="true"
    >
      <svg width={size} height={size} viewBox="0 0 24 24">
        {showAntenna && (
          <g className="nova-avatar__antenna">
            <line x1="8.4" y1="4.6" x2="8.4" y2="6.3" />
            <line x1="15.6" y1="4.6" x2="15.6" y2="6.3" />
            <circle cx="8.4" cy="3.9" r="1.05" />
            <circle cx="15.6" cy="3.9" r="1.05" />
          </g>
        )}
        {/* Khung mặt kiểu "màn hình thiết bị" - nền tối hơn accent 1 sắc
            để tạo chiều sâu lõm vào, viền mảnh màu LED. */}
        <rect className="nova-avatar__frame" x="5.5" y="6.5" width="13" height="11" rx="3.4" />
        {/* 2 thanh LED (rounded rect, không phải chấm tròn) - animation
            áp lên đây theo state, xem globals.css. */}
        <rect className="nova-avatar__eye nova-avatar__eye--left" x="8.7" y="10.7" width="2.6" height="3.6" rx="1.3" />
        <rect className="nova-avatar__eye nova-avatar__eye--right" x="12.7" y="10.7" width="2.6" height="3.6" rx="1.3" />
      </svg>
    </span>
  );
}
