import { useEffect, useRef } from 'react'
import { events } from '../../mocks'
import { eventsApi } from '../../api/services'
import { eventResponseToDomain } from '../../api/mappers'
import { env } from '../../config/env'
import type { PatrolEvent } from '../../types/domain'

// 이미 확인한 긴급 알림 (localStorage) — 한 번 확인하면 재로그인해도 다시 뜨지 않음
const SEEN_KEY = 'emg-seen'
function getSeen(): string[] {
  try {
    return JSON.parse(localStorage.getItem(SEEN_KEY) ?? '[]')
  } catch {
    return []
  }
}
export function isEmergencySeen(id: string) {
  return getSeen().includes(id)
}
export function markEmergencySeen(id: string) {
  const seen = getSeen()
  if (!seen.includes(id)) localStorage.setItem(SEEN_KEY, JSON.stringify([...seen, id]))
}

/**
 * 긴급 알림 수신 (1c+). 진입 시 목록을 훑지 않고, 긴급이 "도착"할 때만 콜백한다.
 * - 실서버: SSE 구독 (백엔드가 긴급 이벤트를 push). 대시보드 이탈 시 연결 해제.
 * - 목업: 위험도 '긴급' 이벤트를 push처럼 1회 전달(확인 여부는 호출측이 판단).
 */
export function useEmergencyAlert(onEmergency: (event: PatrolEvent) => void) {
  const onRef = useRef(onEmergency)
  onRef.current = onEmergency

  useEffect(() => {
    if (env.useMocks) {
      const target = events.find((e) => e.riskLevel === '긴급')
      if (!target) return
      const timer = window.setTimeout(() => onRef.current(target), 1500)
      return () => window.clearTimeout(timer)
    }
    // 실서버 SSE — 엔드포인트/페이로드 스키마는 백엔드 확정 필요
    const controller = new AbortController()
    eventsApi
      .subscribeEmergency((payload) => onRef.current(eventResponseToDomain(payload)), controller.signal)
      .catch(() => {
        // 초기 화면은 유지. 재연결 정책은 백엔드 SSE 정책 확정 후 조정.
      })
    return () => controller.abort()
  }, [])
}
