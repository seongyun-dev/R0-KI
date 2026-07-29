import { useEffect } from 'react'
import type { MapDetailResponse, ZoneCreateResponse, ZoneTypeCode } from '../../api/contracts'
import type { MapViewData } from '../../api/mappers'
import { mapApi } from '../../api/services'
import { env } from '../../config/env'
import { useApiQuery } from '../../lib/useApiQuery'
import { complexMap, mapCheckpoints, mapPins, mapRobot } from '../../mocks'
import type { ZoneType } from '../../types/domain'
import { useAuthStore } from '../auth/useAuthStore'
import { useRegisteredMap } from '../onboarding/useRegisteredMap'

const GRID_COLS = 14
const GRID_ROWS = 7

const zoneTypeLabel: Record<ZoneTypeCode, ZoneType> = {
  START: '출입구',
  PARKING: '주차장',
  RECYCLING_AREA: '분리수거장',
  DANGER_ZONE: '위험구역',
  DESTINATION: '도착지',
}

const zoneIcon: Record<ZoneTypeCode, string> = {
  START: '🚪',
  PARKING: '🅿️',
  RECYCLING_AREA: '♻️',
  DANGER_ZONE: '⚠️',
  DESTINATION: '🏁',
}

function coordinateToGrid(
  detail: MapDetailResponse,
  zone: ZoneCreateResponse,
) {
  const resolution = Number(detail.resolution)
  const originX = Number(detail.originX)
  const originY = Number(detail.originY)
  const minX = Number(zone.minX)
  const maxX = Number(zone.maxX)
  const minY = Number(zone.minY)
  const maxY = Number(zone.maxY)

  const left = ((minX - originX) / resolution / detail.width) * GRID_COLS
  const right = ((maxX - originX) / resolution / detail.width) * GRID_COLS
  const top = ((detail.height - (maxY - originY) / resolution) / detail.height) * GRID_ROWS
  const bottom = ((detail.height - (minY - originY) / resolution) / detail.height) * GRID_ROWS

  return {
    x: Math.max(0, Math.min(GRID_COLS, left)),
    y: Math.max(0, Math.min(GRID_ROWS, top)),
    w: Math.max(0.2, Math.min(GRID_COLS, right) - Math.max(0, left)),
    h: Math.max(0.2, Math.min(GRID_ROWS, bottom) - Math.max(0, top)),
  }
}

function registeredMapToView(
  detail: MapDetailResponse,
  zones: ZoneCreateResponse[],
  mapImageUrl: string,
  robotId: string | number,
): MapViewData {
  const converted = zones.map((zone) => {
    const rect = coordinateToGrid(detail, zone)
    return {
      zone: {
        id: String(zone.zoneId),
        type: zoneTypeLabel[zone.type],
        label: zone.name,
        rect,
      },
      checkpoint: {
        id: String(zone.zoneId),
        icon: zoneIcon[zone.type],
        label: zone.name,
        x: rect.x + rect.w / 2,
        y: rect.y + rect.h / 2,
      },
    }
  })

  return {
    map: {
      cols: GRID_COLS,
      rows: GRID_ROWS,
      zones: converted.map((item) => item.zone),
      mapId: String(detail.mapId),
      mapUrl: detail.mapUrl,
      mapImageUrl,
    },
    robot: {
      id: String(robotId),
      x: GRID_COLS / 2,
      y: GRID_ROWS / 2,
    },
    pins: [],
    checkpoints: converted.map((item) => item.checkpoint),
  }
}

/** 대시보드에 등록된 지도 이미지와 구역을 조회한다. */
export function useComplexMap() {
  const mapId = useAuthStore((state) => state.mapId) ?? env.defaultMapId
  const robotId = useAuthStore((state) => state.robotId) ?? env.defaultRobotId
  const registeredZones = useRegisteredMap((state) => state.zones)

  const query = useApiQuery<{ view: MapViewData }>(
    async () => {
      if (env.useMocks) {
        const map = registeredZones.length ? { ...complexMap, zones: registeredZones } : complexMap
        return {
          view: {
            map,
            robot: mapRobot,
            pins: mapPins,
            checkpoints: mapCheckpoints,
          },
        }
      }
      if (!mapId) throw new Error('등록된 지도 ID가 없습니다.')

      const [detail, zones] = await Promise.all([mapApi.detail(mapId), mapApi.zones(mapId)])
      const blob = await mapApi.file(detail.mapUrl)
      const mapImageUrl = URL.createObjectURL(blob)
      return {
        view: registeredMapToView(detail, zones, mapImageUrl, robotId ?? '로봇'),
      }
    },
    [mapId, robotId, registeredZones],
    { delayMs: env.useMocks ? 350 : 0 },
  )

  const imageUrl = query.data?.view.map.mapImageUrl
  useEffect(
    () => () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl)
    },
    [imageUrl],
  )

  return {
    ...query,
    data: query.data?.view,
  }
}
