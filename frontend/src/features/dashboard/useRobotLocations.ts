import { useEffect, useState } from 'react'
import type {
  RobotLocationEvent,
  RobotMapLocationResponse,
  RobotStatusCode,
} from '../../api/contracts'
import { robotsApi } from '../../api/services'
import { env } from '../../config/env'
import type { ComplexMapData, MapRobot } from '../../types/domain'

const RECONNECT_DELAY_MS = 2_000

function toMapRobot(
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

  const clamp = (value: number, max: number) => Math.max(0, Math.min(max, value))
  const toGridPoint = (x: number | string, y: number | string) => {
    const pixelX = (Number(x) - originX) / resolution
    const pixelY = height - (Number(y) - originY) / resolution
    return {
      x: clamp((pixelX / width) * map.cols, map.cols),
      y: clamp((pixelY / height) * map.rows, map.rows),
    }
  }
  const point = toGridPoint(location.x, location.y)

  return {
    id: String(location.robotId),
    name: 'robotName' in location ? location.robotName : undefined,
    ...point,
    updatedAt: location.locationUpdatedAt ?? undefined,
    ...('routePoints' in location
      ? {
          routePoints: location.routePoints.map((routePoint) => ({
            ...toGridPoint(routePoint.xCoordinate, routePoint.yCoordinate),
            recordedAt: routePoint.recordedAt,
          })),
        }
      : {}),
  }
}

export function useRobotLocations(map: ComplexMapData | undefined) {
  const [locations, setLocations] = useState<MapRobot[]>([])
  const [statuses, setStatuses] = useState<Record<string, RobotStatusCode | string>>({})

  useEffect(() => {
    if (env.useMocks || !map) {
      setLocations([])
      setStatuses({})
      return
    }

    const controller = new AbortController()
    let reconnectTimer: number | undefined

    const updateLocation = (location: RobotLocationEvent | RobotMapLocationResponse) => {
      const mapped = toMapRobot(location, map)
      if (!mapped || controller.signal.aborted) return
      setLocations((current) => {
        const previous = current.find((item) => item.id === mapped.id)
        const next = { ...previous, ...mapped, name: mapped.name ?? previous?.name }
        return [...current.filter((item) => item.id !== mapped.id), next]
      })
    }

    const subscribe = () => {
      robotsApi.subscribeLocations(
        () => undefined,
        updateLocation,
        (statusUpdate) => {
          if (controller.signal.aborted) return
          setStatuses((current) => ({
            ...current,
            [String(statusUpdate.robotId)]: statusUpdate.status,
          }))
        },
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

    robotsApi.locations().then((initial) => {
      if (!controller.signal.aborted) {
        setLocations(initial.flatMap((location) => {
          const mapped = toMapRobot(location, map)
          return mapped ? [mapped] : []
        }))
      }
    }).catch(() => {
      // SSE 연결은 초기 조회 실패와 별개로 유지한다.
    }).finally(() => {
      if (!controller.signal.aborted) subscribe()
    })

    return () => {
      controller.abort()
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
    }
  }, [map])

  return { locations, statuses }
}
