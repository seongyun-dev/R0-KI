import { useEffect, useRef } from 'react'
import { patrols } from '../../mocks'
import { patrolListItemToDomain } from '../../api/mappers'
import { patrolsApi, unwrapList } from '../../api/services'
import { env } from '../../config/env'
import type { Patrol } from '../../types/domain'
import { createSeenStore, usePolledFeed } from './usePolledFeed'

// 이미 확인한 순찰 완료 알림 — 확인하면 새로고침해도 다시 뜨지 않음.
// 보관 상한·저장 실패 처리는 createSeenStore 가 담당한다.
const seen = createSeenStore('patrol-done-seen')
export const isPatrolDoneSeen = seen.isSeen
export const markPatrolDoneSeen = seen.markSeen

/**
 * 순찰 완료 수신. 진입 시 목록을 훑지 않고, 순찰이 "끝날" 때만 콜백한다.
 * - 목업: 완료된 순찰 한 건을 push 처럼 1회 전달(확인 여부는 호출측이 판단).
 * - 실서버: 완료 목록을 주기 조회해 새로 생긴 건만 전달한다.
 *   폴링 정책(가시성·백오프)은 usePolledFeed 가 담당한다.
 *   백엔드에 순찰 완료 SSE 가 열리면 이 훅 안만 구독으로 바꾸면 된다.
 */
export function usePatrolComplete(onComplete: (patrol: Patrol) => void) {
  const onRef = useRef(onComplete)
  onRef.current = onComplete

  useEffect(() => {
    if (!env.useMocks) return
    const target = patrols.find((p) => p.status === '완료')
    if (!target) return
    const timer = window.setTimeout(() => onRef.current(target), 3000)
    return () => window.clearTimeout(timer)
  }, [])

  usePolledFeed({
    enabled: !env.useMocks,
    label: 'usePatrolComplete',
    // 순찰 완료는 즉시성이 필요 없다 — 긴급 알림보다 더 늦춰도 된다
    intervalMs: 20_000,
    fetchItems: async () =>
      unwrapList(
        await patrolsApi.list({
          status: 'COMPLETED',
          page: 0,
          size: 20,
          sort: ['startedAt,DESC'],
        }),
      ),
    getId: (item) => String(item.patrolId),
    toDomain: patrolListItemToDomain,
    onNew: (patrol) => onRef.current(patrol),
  })
}
