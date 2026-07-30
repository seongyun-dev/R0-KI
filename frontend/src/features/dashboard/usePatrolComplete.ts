import { useEffect, useRef } from 'react'
import { patrols } from '../../mocks'
import { patrolListItemToDomain } from '../../api/mappers'
import { patrolsApi } from '../../api/services'
import { env } from '../../config/env'
import type { Patrol } from '../../types/domain'

// 이미 확인한 순찰 완료 알림 (localStorage) — 확인하면 새로고침해도 다시 뜨지 않음
const SEEN_KEY = 'patrol-done-seen'
function getSeen(): string[] {
  try {
    return JSON.parse(localStorage.getItem(SEEN_KEY) ?? '[]')
  } catch {
    return []
  }
}
export function isPatrolDoneSeen(id: string) {
  return getSeen().includes(id)
}
export function markPatrolDoneSeen(id: string) {
  const seen = getSeen()
  if (!seen.includes(id)) localStorage.setItem(SEEN_KEY, JSON.stringify([...seen, id]))
}

/**
 * 순찰 완료 수신. 진입 시 목록을 훑지 않고, 순찰이 "끝날" 때만 콜백한다.
 * - 목업: 완료된 순찰 한 건을 push 처럼 1회 전달(확인 여부는 호출측이 판단).
 * - 실서버: 완료 목록을 주기 조회해 새로 생긴 건만 전달한다.
 *   백엔드에 순찰 완료 SSE 가 열리면 이 훅 안만 구독으로 바꾸면 된다
 *   (긴급 알림 useEmergencyAlert 과 같은 구조).
 */
export function usePatrolComplete(onComplete: (patrol: Patrol) => void) {
  const onRef = useRef(onComplete)
  onRef.current = onComplete

  useEffect(() => {
    if (env.useMocks) {
      const target = patrols.find((p) => p.status === '완료')
      if (!target) return
      const timer = window.setTimeout(() => onRef.current(target), 3000)
      return () => window.clearTimeout(timer)
    }

    let disposed = false
    let initialized = false
    const knownIds = new Set<string>()

    const poll = async () => {
      try {
        const response = await patrolsApi.list({
          status: 'COMPLETED',
          page: 0,
          size: 20,
          sort: ['startedAt,DESC'],
        })
        if (disposed) return

        const items = response.content
        if (initialized) {
          const added = items.filter((item) => !knownIds.has(String(item.patrolId)))
          if (added.length > 0) onRef.current(patrolListItemToDomain(added[0]))
        }
        items.forEach((item) => knownIds.add(String(item.patrolId)))
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
