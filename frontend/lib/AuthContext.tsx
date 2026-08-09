"use client";

/**
 * Nơi DUY NHẤT lưu trạng thái "ai đang đăng nhập, role gì" cho toàn bộ
 * Frontend - mọi trang/component đọc qua useAuth(), không tự gọi
 * GET /v1/auth/me rải rác ở nhiều nơi.
 *
 * Vì sao cần Context thay vì chỉ gọi API trong từng trang: role quyết
 * định TOÀN BỘ giao diện hiển thị (sidebar, trang nào được vào) - nếu
 * mỗi trang tự gọi /me riêng, có lúc trang này thấy role cũ, trang kia
 * thấy role mới (do cache/timing khác nhau), gây giao diện không nhất
 * quán. Load 1 lần lúc app khởi động, chia sẻ cho toàn bộ cây component.
 */

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, ApiError, UserPublic } from "./api";

interface AuthContextValue {
  user: UserPublic | null;
  loading: boolean;
  refreshUser: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = async () => {
    try {
      const me = await api.get<UserPublic>("/v1/auth/me");
      setUser(me);
    } catch (err) {
      // 401 nghĩa là chưa đăng nhập/hết hạn - đây là trạng thái BÌNH
      // THƯỜNG (không phải lỗi hệ thống), không log ra console gây
      // nhiễu, chỉ đơn giản coi như chưa có user.
      if (!(err instanceof ApiError && err.status === 401)) {
        console.error("Không thể tải thông tin người dùng:", err);
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    await api.post("/v1/auth/logout");
    setUser(null);
  };

  useEffect(() => {
    refreshUser();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, refreshUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() phải được gọi bên trong <AuthProvider>");
  return ctx;
}
