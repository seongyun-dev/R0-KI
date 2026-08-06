import { useEffect, useRef } from 'react'
import { emergencyEventSseToDomain } from '../../api/mappers'
import { eventsApi } from '../../api/services'
import type { PatrolEvent } from '../../types/domain'
import { createSeenStore } from './usePolledFeed'

const RECONNECT_DELAY_MS = 2_000
const seen = createSeenStore('emg-seen')

export const isEmergencySeen = seen.isSeen
export const markEmergencySeen = seen.markSeen

export function useEmergencyAlert(onEmergency: (event: PatrolEvent) => void) {
  const onRef = useRef(onEmergency)
  onRef.current = onEmergency


  useEffect(() => {

    const controller = new AbortController()
    let reconnectTimer: number | undefined

    const subscribe = () => {
      eventsApi
        .subscribeEmergency(
          (event) => onRef.current(emergencyEventSseToDomain(event)),
          controller.signal,
        )
        .then(() => {
          if (!controller.signal.aborted) {
            reconnectTimer = window.setTimeout(subscribe, RECONNECT_DELAY_MS)
          }
        })
        .catch(() => {
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
