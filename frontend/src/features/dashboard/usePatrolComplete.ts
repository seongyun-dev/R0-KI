import { useEffect, useRef } from 'react'
import type { PatrolCompletedSseEvent } from '../../api/contracts'
import { eventsApi } from '../../api/services'
import { env } from '../../config/env'
import { patrols } from '../../mocks'
import { createSeenStore } from './usePolledFeed'

const RECONNECT_DELAY_MS = 2_000
const seen = createSeenStore('patrol-done-seen')

export const isPatrolDoneSeen = seen.isSeen
export const markPatrolDoneSeen = seen.markSeen

export function usePatrolComplete(
  onComplete: (patrol: PatrolCompletedSseEvent) => void,
) {
  const onRef = useRef(onComplete)
  onRef.current = onComplete

  useEffect(() => {
    if (env.useMocks) {
      const target = patrols.find((patrol) => patrol.status === '완료')
      if (!target) return
      const timer = window.setTimeout(
        () =>
          onRef.current({
            patrolId: Number(target.backendId ?? target.id),
            robotId: Number(target.robotId),
            robotName: target.robotName ?? target.robotId,
            completedAt: new Date().toISOString(),
          }),
        3_000,
      )
      return () => window.clearTimeout(timer)
    }

    const controller = new AbortController()
    let reconnectTimer: number | undefined

    const subscribe = () => {
      eventsApi.subscribeGeneral(
        (event) => onRef.current(event),
        controller.signal,
      ).then(() => {
        if (!controller.signal.aborted) {
          reconnectTimer = window.setTimeout(subscribe, RECONNECT_DELAY_MS)
        }
      }).catch(() => {
        if (!controller.signal.aborted) {
          reconnectTimer = window.setTimeout(subscribe, RECONNECT_DELAY_MS)
        }
      })
    }

    subscribe()
    return () => {
      controller.abort()
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
    }
  }, [])
}
