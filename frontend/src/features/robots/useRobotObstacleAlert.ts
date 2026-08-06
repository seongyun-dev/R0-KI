import { useEffect, useRef } from 'react'
import type { RobotObstacleEvent } from '../../api/contracts'
import { robotsApi } from '../../api/services'

const RECONNECT_DELAY_MS = 2_000

export function useRobotObstacleAlert(
  onEvent: (event: RobotObstacleEvent) => void,
) {
  const onRef = useRef(onEvent)
  onRef.current = onEvent

  useEffect(() => {

    const controller = new AbortController()
    let reconnectTimer: number | undefined

    const subscribe = () => {
      robotsApi
        .subscribeObstacleEvents(
          (event) => onRef.current(event),
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
