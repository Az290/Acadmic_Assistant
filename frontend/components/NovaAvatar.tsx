import Image from "next/image";

/** Trạng thái hoạt động thật của Nova trong pipeline chat. */
export type NovaState = "idle" | "checking" | "searching" | "generating";

/**
 * Avatar dùng chung cho nút chat, header và tin nhắn của Nova.
 * Ảnh đầu robot được tách riêng để không lặp lại mascot toàn thân ở banner.
 */
export default function NovaAvatar({
  size = 28,
  state = "idle",
}: {
  size?: number;
  state?: NovaState;
}) {
  return (
    <span
      className={`nova-avatar nova-avatar--${state}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <Image
        src="/nova-head.png"
        alt=""
        width={size}
        height={size}
        sizes={`${size}px`}
        className="h-full w-full object-contain"
      />
    </span>
  );
}
