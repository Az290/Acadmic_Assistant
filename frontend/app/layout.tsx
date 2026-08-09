import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/AuthContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Academic Assistant",
  description: "Trợ lý học thuật đa agent",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="vi"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      // Một số extension trình duyệt (trình quản lý mật khẩu, công cụ
      // AI phụ trợ...) tự chèn thuộc tính lạ (vd data-yd-*) thẳng vào
      // <html> SAU KHI trang đã tải - React so HTML server render với
      // HTML thực tế trên trình duyệt thấy khác nên báo "hydration
      // mismatch". Đây KHÔNG PHẢI lỗi trong code của app (đã xác nhận
      // qua log: thuộc tính lạ không tồn tại ở phía server) - chỉ tắt
      // cảnh báo ở ĐÚNG phần tử <html> này, không che giấu bất kỳ lỗi
      // hydration thật nào khác có thể xảy ra ở nơi khác trong app.
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col bg-slate-50 text-slate-900">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
