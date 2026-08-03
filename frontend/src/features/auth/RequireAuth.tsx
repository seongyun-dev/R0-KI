import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import type { PatrolEvent } from '../../types/domain'
import type { RobotObstacleEvent } from '../../api/contracts'
import { EmergencyAlertModal } from '../dashboard/EmergencyAlertModal'
import {
  isEmergencySeen,
  markEmergencySeen,
  useEmergencyAlert,
} from '../dashboard/useEmergencyAlert'
import { useAuthStore } from './useAuthStore'
import { useOnboardingProgress } from '../onboarding/useOnboardingProgress'
import { RobotObstacleAlertModal } from '../robots/RobotObstacleAlertModal'
import { useRobotObstacleAlert } from '../robots/useRobotObstacleAlert'

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
  const navigate = useNavigate()
  const [alertEvent, setAlertEvent] = useState<PatrolEvent | null>(null)
  const [obstacleEvent, setObstacleEvent] = useState<RobotObstacleEvent | null>(null)

  useEmergencyAlert((event) => {
    if (!isEmergencySeen(event.id)) setAlertEvent(event)
  })

  useRobotObstacleAlert((event) => {
    if (event.status === 'STOP') {
      setObstacleEvent(event)
    } else {
      setObstacleEvent((current) =>
        current?.robotId === event.robotId ? null : current,
      )
    }
  })

  const dismissAlert = () => {
    if (alertEvent) markEmergencySeen(alertEvent.id)
    setAlertEvent(null)
  }

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
  return (
    <>
      {children}
      {alertEvent && (
        <EmergencyAlertModal
          open
          event={alertEvent}
          onClose={dismissAlert}
          onConfirm={() => {
            const eventId = alertEvent.id
            dismissAlert()
            navigate(`/app/events/${eventId}`)
          }}
        />
      )}
      {obstacleEvent && !alertEvent && (
        <RobotObstacleAlertModal
          event={obstacleEvent}
          onClose={() => setObstacleEvent(null)}
        />
      )}
    </>
  )
}
