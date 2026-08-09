import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type AuthState = {
  loginId: string | null
  accessToken: string | null
  mapId: string | null
  robotId: string | null
  isAuthenticated: boolean
  login: (
    loginId: string,
    accessToken?: string,
    context?: { mapId?: string | number; robotId?: string | number },
  ) => void
  logout: () => void
}

/** 가벼운 인증 상태 — 서버 연동 시 토큰/세션으로 교체 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      loginId: null,
      accessToken: null,
      mapId: null,
      robotId: null,
      isAuthenticated: false,
      login: (loginId, accessToken = 'mock-access-token', context) =>
        set({
          loginId,
          accessToken,
          mapId: context?.mapId == null ? null : String(context.mapId),
          robotId: context?.robotId == null ? null : String(context.robotId),
          isAuthenticated: true,
        }),
      logout: () =>
        set({
          loginId: null,
          accessToken: null,
          mapId: null,
          robotId: null,
          isAuthenticated: false,
        }),
    }),
    { name: 'patrol-auth' },
  ),
)
