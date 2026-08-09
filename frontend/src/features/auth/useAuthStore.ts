import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

const AUTH_STORAGE_KEY = 'patrol-auth'
const SESSION_MODE_KEY = 'patrol-auth-session-mode'
const MAX_ACCESS_TOKEN_AGE_MS = 8 * 60 * 60 * 1000

const usesSessionStorage = () => sessionStorage.getItem(SESSION_MODE_KEY) === 'true'

const authStorage = {
  getItem: (name: string) =>
    (usesSessionStorage() ? sessionStorage : localStorage).getItem(name),
  setItem: (name: string, value: string) => {
    const target = usesSessionStorage() ? sessionStorage : localStorage
    const other = usesSessionStorage() ? localStorage : sessionStorage
    target.setItem(name, value)
    other.removeItem(name)
  },
  removeItem: (name: string) => {
    localStorage.removeItem(name)
    sessionStorage.removeItem(name)
  },
}

export function setAuthPersistence(remember: boolean) {
  const current = localStorage.getItem(AUTH_STORAGE_KEY) ?? sessionStorage.getItem(AUTH_STORAGE_KEY)

  if (remember) {
    sessionStorage.removeItem(SESSION_MODE_KEY)
    if (current) localStorage.setItem(AUTH_STORAGE_KEY, current)
    sessionStorage.removeItem(AUTH_STORAGE_KEY)
  } else {
    sessionStorage.setItem(SESSION_MODE_KEY, 'true')
    if (current) sessionStorage.setItem(AUTH_STORAGE_KEY, current)
    localStorage.removeItem(AUTH_STORAGE_KEY)
  }
}

function accessTokenExpiration(accessToken: string) {
  const maximumExpiration = Date.now() + MAX_ACCESS_TOKEN_AGE_MS

  try {
    const encodedPayload = accessToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const paddedPayload = encodedPayload.padEnd(Math.ceil(encodedPayload.length / 4) * 4, '=')
    const payload = JSON.parse(atob(paddedPayload)) as {
      exp?: number
    }
    return payload.exp == null
      ? maximumExpiration
      : Math.min(payload.exp * 1000, maximumExpiration)
  } catch {
    return maximumExpiration
  }
}

type AuthState = {
  loginId: string | null
  memberName: string | null
  accessToken: string | null
  accessTokenExpiresAt: number | null
  mapId: string | null
  robotId: string | null
  contextByLoginId: Record<string, { mapId: string | null; robotId: string | null }>
  isAuthenticated: boolean
  setMapContext: (context: {
    mapId?: string | number | null
    robotId?: string | number | null
  }) => void
  login: (loginId: string, memberName: string, accessToken: string) => void
  logout: () => void
}

type PersistedAuthState = Pick<
  AuthState,
  | 'loginId'
  | 'memberName'
  | 'accessToken'
  | 'accessTokenExpiresAt'
  | 'mapId'
  | 'robotId'
  | 'contextByLoginId'
  | 'isAuthenticated'
>

const EMPTY_AUTH_STATE: PersistedAuthState = {
  loginId: null,
  memberName: null,
  accessToken: null,
  accessTokenExpiresAt: null,
  mapId: null,
  robotId: null,
  contextByLoginId: {},
  isAuthenticated: false,
}

function migrateAuthState(persistedState: unknown, version: number): PersistedAuthState {
  const previous =
    persistedState && typeof persistedState === 'object'
      ? (persistedState as Partial<PersistedAuthState>)
      : {}
  const contextByLoginId =
    previous.contextByLoginId && typeof previous.contextByLoginId === 'object'
      ? previous.contextByLoginId
      : {}

  // v0에는 토큰 만료시각이 없을 수 있으므로 인증은 안전하게 초기화하고 계정별 UI context만 보존한다.
  if (version < 1) {
    return { ...EMPTY_AUTH_STATE, contextByLoginId }
  }

  const hasValidToken =
    typeof previous.accessToken === 'string' &&
    typeof previous.accessTokenExpiresAt === 'number' &&
    previous.accessTokenExpiresAt > Date.now()

  return {
    loginId: hasValidToken && typeof previous.loginId === 'string' ? previous.loginId : null,
    memberName: hasValidToken && typeof previous.memberName === 'string' ? previous.memberName : null,
    accessToken: hasValidToken ? previous.accessToken ?? null : null,
    accessTokenExpiresAt: hasValidToken ? previous.accessTokenExpiresAt ?? null : null,
    mapId: hasValidToken && typeof previous.mapId === 'string' ? previous.mapId : null,
    robotId: hasValidToken && typeof previous.robotId === 'string' ? previous.robotId : null,
    contextByLoginId,
    isAuthenticated: hasValidToken,
  }
}

/** 가벼운 인증 상태 — 서버 연동 시 토큰/세션으로 교체 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      loginId: null,
      memberName: null,
      accessToken: null,
      accessTokenExpiresAt: null,
      mapId: null,
      robotId: null,
      contextByLoginId: {},
      isAuthenticated: false,
      setMapContext: (context) =>
        set((state) => {
          const mapId =
            context.mapId === undefined
              ? state.mapId
              : context.mapId === null
                ? null
                : String(context.mapId)
          const robotId =
            context.robotId === undefined
              ? state.robotId
              : context.robotId === null
                ? null
                : String(context.robotId)

          return {
            mapId,
            robotId,
            contextByLoginId:
              state.loginId == null
                ? state.contextByLoginId
                : {
                    ...state.contextByLoginId,
                    [state.loginId]: { mapId, robotId },
                  },
          }
        }),
      login: (loginId, memberName, accessToken) => {
        if (!accessToken) {
          throw new Error('로그인 토큰이 없습니다.')
        }
        const normalizedLoginId = loginId.trim()
        set((state) => {
          const savedContext = state.contextByLoginId[normalizedLoginId]
          return {
            loginId: normalizedLoginId,
            memberName: memberName.trim(),
            accessToken,
            accessTokenExpiresAt: accessTokenExpiration(accessToken),
            mapId: savedContext?.mapId ?? null,
            robotId: savedContext?.robotId ?? null,
            isAuthenticated: true,
          }
        })
      },
      logout: () =>
        set({
          loginId: null,
          memberName: null,
          accessToken: null,
          accessTokenExpiresAt: null,
          mapId: null,
          robotId: null,
          isAuthenticated: false,
        }),
    }),
    {
      name: AUTH_STORAGE_KEY,
      storage: createJSONStorage(() => authStorage),
      version: 1,
      migrate: migrateAuthState,
      partialize: ({
        loginId,
        memberName,
        accessToken,
        accessTokenExpiresAt,
        mapId,
        robotId,
        contextByLoginId,
        isAuthenticated,
      }) => ({
        loginId,
        memberName,
        accessToken,
        accessTokenExpiresAt,
        mapId,
        robotId,
        contextByLoginId,
        isAuthenticated,
      }),
    },
  ),
)
