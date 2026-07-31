import { useEffect, useRef } from 'react'
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

  // 격자 1칸의 실제 거리 — 지도 가로(px)×resolution(m/px)을 열 수로 나눈다. 축척 표기용
  const resolution = Number(detail.resolution)
  const metersPerCell =
    Number.isFinite(resolution) && resolution > 0 && detail.width
      ? (detail.width * resolution) / GRID_COLS
      : undefined

  return {
    map: {
      cols: GRID_COLS,
      rows: GRID_ROWS,
      zones: converted.map((item) => item.zone),
      mapId: String(detail.mapId),
      mapUrl: detail.mapUrl,
      mapImageUrl,
      metersPerCell,
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
  // 이 훅이 만든 objectURL 전부 — 화면에 못 올라간 것까지 회수하기 위해 들고 있는다
  const createdUrls = useRef<string[]>([])

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
      createdUrls.current.push(mapImageUrl)
      return {
        view: registeredMapToView(detail, zones, mapImageUrl, robotId ?? '로봇'),
      }
    },
    [mapId, robotId, registeredZones],
    { delayMs: env.useMocks ? 350 : 0 },
  )

  /* objectURL 회수 — state 에 들어온 것만 보고 지우면 누수가 남는다.
     조회 중 화면을 벗어나면 blob 은 이미 받아 URL 까지 만들어졌는데
     useApiQuery 가 결과를 버려서(active=false) 회수 대상에서 빠지기 때문이다.
     그래서 만든 URL 을 전부 ref 에 적어두고, 지금 쓰는 것만 남긴다. */
  const imageUrl = query.data?.view.map.mapImageUrl
  useEffect(() => {
    createdUrls.current = createdUrls.current.filter((url) => {
      if (url === imageUrl) return true
      URL.revokeObjectURL(url)
      return false
    })
  }, [imageUrl])
  useEffect(
    () => () => {
      createdUrls.current.forEach((url) => URL.revokeObjectURL(url))
      createdUrls.current = []
    },
    [],
  )

  return {
    ...query,
    data: query.data?.view,
  }
}
