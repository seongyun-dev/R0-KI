import { useEffect, useRef } from 'react'
import type {
  MapDetailResponse,
  NavigationWaypointResponse,
  WaypointActionCode,
  ZoneCreateResponse,
  ZoneTypeCode,
} from '../../api/contracts'
import type { MapViewData } from '../../api/mappers'
import { mapApi } from '../../api/services'
import { env } from '../../config/env'
import { useApiQuery } from '../../lib/useApiQuery'
import type { ZoneType } from '../../types/domain'
import { useAuthStore } from '../auth/useAuthStore'
import {
  worldBoundsToGridRect,
  worldToMapRatios,
  zoneBounds,
} from '../onboarding/mapCoordinates'
import { useRegisteredMap } from '../onboarding/useRegisteredMap'

const GRID_COLS = 14
const GRID_ROWS = 7

const zoneTypeLabel: Record<ZoneTypeCode, ZoneType> = {
  START: '출입구',
  PARKING: '주차장',
  RECYCLING_AREA: '분리수거장',
  DESTINATION: '도착지',
}

const zoneIcon: Record<ZoneTypeCode, string> = {
  START: '🚪',
  PARKING: '🅿️',
  RECYCLING_AREA: '♻️',
  DESTINATION: '🏁',
}

const waypointLabel: Record<WaypointActionCode, string> = {
  PASS: '경유',
  SCAN: '탐지',
  DESTINATION: '도착지',
}

const waypointIcon: Record<WaypointActionCode, string> = {
  PASS: '●',
  SCAN: '◎',
  DESTINATION: '🏁',
}

function registeredMapToView(
  detail: MapDetailResponse,
  zones: ZoneCreateResponse[],
  waypoints: NavigationWaypointResponse[],
  mapImageUrl: string,
  robotId: string | number,
): MapViewData {
  const converted = zones.map((zone) => {
    const bounds = zoneBounds(zone)
    const rect = worldBoundsToGridRect(detail, bounds, GRID_COLS, GRID_ROWS)
    return {
      zone: {
        id: String(zone.zoneId),
        type: zoneTypeLabel[zone.type],
        label: zone.name,
        rect,
        worldBounds: bounds,
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

  const zoneNames = new Map(zones.map((zone) => [String(zone.zoneId), zone.name]))
  const checkpoints = [...waypoints]
    .sort((left, right) => left.sequence - right.sequence)
    .map((waypoint) => {
      const ratios = worldToMapRatios(detail, {
        x: Number(waypoint.x),
        y: Number(waypoint.y),
      })
      const actionLabel = waypointLabel[waypoint.action]
      const linkedZone = waypoint.zoneId == null ? undefined : zoneNames.get(String(waypoint.zoneId))
      return {
        id: String(waypoint.waypointId),
        icon: waypointIcon[waypoint.action],
        label: linkedZone ? `${actionLabel} · ${linkedZone}` : actionLabel,
        x: Math.max(0, Math.min(GRID_COLS, ratios.xRatio * GRID_COLS)),
        y: Math.max(0, Math.min(GRID_ROWS, ratios.yRatio * GRID_ROWS)),
        worldX: Number(waypoint.x),
        worldY: Number(waypoint.y),
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
      metersPerCell,
      resolution,
      originX: Number(detail.originX),
      originY: Number(detail.originY),
      originYaw: Number(detail.originYaw),
      pixelWidth: detail.width,
      pixelHeight: detail.height,
    },
    robot: {
      id: String(robotId),
      x: GRID_COLS / 2,
      y: GRID_ROWS / 2,
    },
    pins: [],
    checkpoints,
  }
}

/** 대시보드에 등록된 지도 이미지와 구역을 조회한다. */
export function useComplexMap() {
  const mapId = useAuthStore((state) => state.mapId)
  const robotId = useAuthStore((state) => state.robotId) ?? env.defaultRobotId
  const registeredZones = useRegisteredMap((state) => state.zones)
  // 이 훅이 만든 objectURL 전부 — 화면에 못 올라간 것까지 회수하기 위해 들고 있는다
  const createdUrls = useRef<string[]>([])

  const query = useApiQuery<{ view: MapViewData }>(
    async () => {

      if (!mapId) throw new Error('등록된 지도 ID가 없습니다.')

      const [detail, zones, navigation] = await Promise.all([
        mapApi.detail(mapId),
        mapApi.zones(mapId),
        mapApi.waypoints(mapId),
      ])
      const blob = await mapApi.file(detail.mapUrl)
      const mapImageUrl = URL.createObjectURL(blob)
      createdUrls.current.push(mapImageUrl)
      return {
        view: registeredMapToView(
          detail,
          zones,
          navigation.waypoints,
          mapImageUrl,
          robotId ?? '로봇',
        ),
      }
    },
    [mapId, robotId, registeredZones],
    { delayMs: 0 },
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
