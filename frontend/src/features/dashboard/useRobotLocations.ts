import { useEffect, useState } from 'react'
import type {
  RobotLocationEvent,
  RobotMapLocationResponse,
  RobotStatusCode,
} from '../../api/contracts'
import { robotsApi } from '../../api/services'
import type { ComplexMapData, MapRobot } from '../../types/domain'
import { worldToDashboardGrid } from './mapCoordinateMetadata'

const RECONNECT_DELAY_MS = 2_000
const STATUS_TTL_MS = 15_000

export function toMapRobot(
  location: RobotLocationEvent | RobotMapLocationResponse,
  map: ComplexMapData,
): MapRobot | undefined {
  if (location.x == null || location.y == null) return undefined

  const resolution = map.resolution
  const width = map.pixelWidth
  const height = map.pixelHeight
  const originX = map.originX
  const originY = map.originY
  if (!resolution || !width || !height || originX == null || originY == null) {
    return undefined
  }

  const toGridPoint = (x: number | string, y: number | string) => {
    const worldX = Number(x)
    const worldY = Number(y)
    return worldToDashboardGrid(map, { x: worldX, y: worldY })
  }
  const point = toGridPoint(location.x, location.y)
  if (!point) return undefined

  return {
    id: String(location.robotId),
    name: 'robotName' in location ? location.robotName : undefined,
    ...point,
    ...(location.heading == null ? {} : { heading: Number(location.heading) }),
    updatedAt: location.locationUpdatedAt ?? undefined,
    ...('routePoints' in location
      ? {
          routePoints: location.routePoints.flatMap((routePoint) => {
            const routePointPosition = toGridPoint(
              routePoint.xCoordinate,
              routePoint.yCoordinate,
            )
            return routePointPosition
              ? [{ ...routePointPosition, recordedAt: routePoint.recordedAt }]
              : []
          }),
        }
      : {}),
  }
}

export function useRobotLocations(map: ComplexMapData | undefined) {
  const [locations, setLocations] = useState<MapRobot[]>([])
  const [statuses, setStatuses] = useState<Record<string, RobotStatusCode | string>>({})

  useEffect(() => {

    const controller = new AbortController()
    let reconnectTimer: number | undefined
    let connectionGeneration = 0
    const statusExpiryTimers = new Map<string, number>()

    if (!map) setLocations([])
    setStatuses({})

    const clearStatusExpiryTimers = () => {
      statusExpiryTimers.forEach((timer) => window.clearTimeout(timer))
      statusExpiryTimers.clear()
    }

    const clearLiveStatuses = () => {
      clearStatusExpiryTimers()
      setStatuses({})
    }

    const updateStatus = (
      robotId: string | number,
      status: RobotStatusCode | string,
      generation: number,
    ) => {
      if (controller.signal.aborted || generation !== connectionGeneration) return
      const key = String(robotId)
      const previousTimer = statusExpiryTimers.get(key)
      if (previousTimer !== undefined) window.clearTimeout(previousTimer)

      setStatuses((current) => ({ ...current, [key]: status }))
      const expiryTimer = window.setTimeout(() => {
        if (controller.signal.aborted || generation !== connectionGeneration) return
        statusExpiryTimers.delete(key)
        setStatuses((current) => {
          if (!(key in current)) return current
          const next = { ...current }
          delete next[key]
          return next
        })
      }, STATUS_TTL_MS)
      statusExpiryTimers.set(key, expiryTimer)
    }

    const updateLocation = (
      location: RobotLocationEvent | RobotMapLocationResponse,
      generation: number,
    ) => {
      if (!map || controller.signal.aborted || generation !== connectionGeneration) return
      const mapped = toMapRobot(location, map)
      if (!mapped) return
      setLocations((current) => {
        const previous = current.find((item) => item.id === mapped.id)
        const next = { ...previous, ...mapped, name: mapped.name ?? previous?.name }
        return [...current.filter((item) => item.id !== mapped.id), next]
      })
    }

    const refreshSnapshot = (generation: number) => {
      if (!map) return
      void robotsApi.locations()
        .then((initial) => {
          if (controller.signal.aborted || generation !== connectionGeneration) return
          setLocations(initial.flatMap((location) => {
            const mapped = toMapRobot(location, map)
            return mapped ? [mapped] : []
          }))
        })
        .catch(() => {
          // snapshot 실패와 별개로 SSE heartbeat를 기다린다.
        })
    }

    const scheduleReconnect = (generation: number) => {
      if (controller.signal.aborted || generation !== connectionGeneration) return
      connectionGeneration += 1
      // 단절 중 OFFLINE/IDLE 전환을 놓칠 수 있으므로 이전 PATROLLING 상태를 즉시 폐기한다.
      clearLiveStatuses()
      reconnectTimer = window.setTimeout(subscribe, RECONNECT_DELAY_MS)
    }

    const subscribe = () => {
      if (controller.signal.aborted) return
      const generation = ++connectionGeneration
      refreshSnapshot(generation)

      void robotsApi.subscribeLocations(
        (initial) => initial.forEach((location) => updateLocation(location, generation)),
        (location) => updateLocation(location, generation),
        (statusUpdate) => {
          updateStatus(statusUpdate.robotId, statusUpdate.status, generation)
        },
        controller.signal,
      ).then(
        () => scheduleReconnect(generation),
        () => scheduleReconnect(generation),
      )
    }

    subscribe()

    return () => {
      controller.abort()
      connectionGeneration += 1
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      clearStatusExpiryTimers()
    }
  }, [map])

  return { locations, statuses }
}
