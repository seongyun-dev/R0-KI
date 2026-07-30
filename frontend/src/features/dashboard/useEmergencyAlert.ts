import { useEffect, useRef } from 'react'
import { events } from '../../mocks'
import { eventsApi } from '../../api/services'
import { eventListItemToDomain } from '../../api/mappers'
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

    // 로봇이 POST /api/robot/events로 등록한 응급 이벤트를 관리자용 목록 API에서 확인한다.
    // 최초 조회 결과는 기존 이벤트로 간주하고, 이후 새로 생긴 이벤트만 알림으로 전달한다.
    let disposed = false
    let initialized = false
    const knownIds = new Set<string>()

    const poll = async () => {
      try {
        const response = await eventsApi.list({
          type: 'EMERGENCY',
          page: 0,
          size: 20,
          sort: ['occurredAt,DESC'],
        })
        if (disposed) return

        const items = response.content
        if (initialized) {
          const added = items.filter((item) => !knownIds.has(String(item.eventId)))
          if (added.length > 0) onRef.current(eventListItemToDomain(added[0]))
        }
        items.forEach((item) => knownIds.add(String(item.eventId)))
        initialized = true
      } catch {
        // 일시적인 조회 실패는 다음 주기에 다시 시도한다.
      }
    }

    void poll()
    const timer = window.setInterval(() => void poll(), 5000)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [])
}
