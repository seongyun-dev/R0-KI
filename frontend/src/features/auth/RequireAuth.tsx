import { useEffect, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from './useAuthStore'
import { useOnboardingProgress } from '../onboarding/useOnboardingProgress'

/** 비로그인 접근 차단 — 로그인 후 원래 가려던 곳으로 복귀 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const accessToken = useAuthStore((s) => s.accessToken)
  const accessTokenExpiresAt = useAuthStore((s) => s.accessTokenExpiresAt)
  const loginId = useAuthStore((s) => s.loginId)
  const logout = useAuthStore((s) => s.logout)
  const onboardingOwner = useOnboardingProgress((s) => s.ownerLoginId)
  const onboardingPhase = useOnboardingProgress((s) => s.phase)
  const location = useLocation()

  const hasValidToken =
    isAuthenticated &&
    Boolean(accessToken) &&
    accessTokenExpiresAt != null &&
    accessTokenExpiresAt > Date.now()

  useEffect(() => {
    if (!hasValidToken || accessTokenExpiresAt == null) return
    const timer = window.setTimeout(logout, accessTokenExpiresAt - Date.now())
    return () => window.clearTimeout(timer)
  }, [accessTokenExpiresAt, hasValidToken, logout])

  if (!hasValidToken) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  if (onboardingPhase && onboardingOwner === loginId) {
    return <Navigate to="/signup/onboarding" replace />
  }
  return <>{children}</>
}
