import { useEffect, useRef } from 'react'
import { events } from '../../mocks'
import { eventsApi, unwrapList } from '../../api/services'
import { eventListItemToDomain } from '../../api/mappers'
import { env } from '../../config/env'
import type { PatrolEvent } from '../../types/domain'
import { createSeenStore, usePolledFeed } from './usePolledFeed'

// 이미 확인한 긴급 알림 — 한 번 확인하면 재로그인해도 다시 뜨지 않음.
// 보관 상한·저장 실패 처리는 createSeenStore 가 담당한다.
const seen = createSeenStore('emg-seen')
export const isEmergencySeen = seen.isSeen
export const markEmergencySeen = seen.markSeen

/**
 * 긴급 알림 수신 (1c+). 진입 시 목록을 훑지 않고, 긴급이 "도착"할 때만 콜백한다.
 * - 실서버: 로봇이 POST /api/robot/events 로 등록한 응급 이벤트를 관리자용 목록 API로 확인.
 *   폴링 정책(가시성·백오프)은 usePolledFeed 가 담당한다.
 *   백엔드에 긴급 SSE 가 열리면 이 훅 안만 구독으로 바꾸면 된다.
 * - 목업: 위험도 '긴급' 이벤트를 push처럼 1회 전달(확인 여부는 호출측이 판단).
 */
export function useEmergencyAlert(onEmergency: (event: PatrolEvent) => void) {
  const onRef = useRef(onEmergency)
  onRef.current = onEmergency

  useEffect(() => {
    if (!env.useMocks) return
    const target = events.find((e) => e.riskLevel === '긴급')
    if (!target) return
    const timer = window.setTimeout(() => onRef.current(target), 1500)
    return () => window.clearTimeout(timer)
  }, [])

  usePolledFeed({
    enabled: !env.useMocks,
    label: 'useEmergencyAlert',
    // 종일 띄워두는 화면이라 5초는 과하다. 긴급이라 가장 짧게 두되 10초로 늦춘다
    intervalMs: 10_000,
    fetchItems: async () =>
      unwrapList(
        await eventsApi.list({
          type: 'EMERGENCY',
          page: 0,
          size: 20,
          sort: ['occurredAt,DESC'],
        }),
      ),
    getId: (item) => String(item.eventId),
    toDomain: eventListItemToDomain,
    onNew: (event) => onRef.current(event),
  })
}
