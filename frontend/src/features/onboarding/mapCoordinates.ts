import type { MapDetailResponse, ZoneCreateResponse } from '../../api/contracts'

export type GridRect = { x: number; y: number; w: number; h: number }
export type MapPoint = { x: number; y: number }
export type MapRatios = { xRatio: number; yRatio: number }
export type WorldBounds = { minX: number; minY: number; maxX: number; maxY: number }

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value))

function numericMetadata(map: MapDetailResponse) {
  const resolution = Number(map.resolution)
  const originX = Number(map.originX)
  const originY = Number(map.originY)
  const originYaw = Number(map.originYaw)
  if (
    !Number.isFinite(resolution) || resolution <= 0 ||
    !Number.isFinite(originX) || !Number.isFinite(originY) ||
    !Number.isFinite(originYaw) ||
    !Number.isFinite(map.width) || map.width <= 0 ||
    !Number.isFinite(map.height) || map.height <= 0
  ) {
    throw new Error('지도 좌표 메타데이터가 올바르지 않습니다.')
  }
  if (Math.abs(originYaw) > 1e-6) {
    throw new Error('회전된 지도(originYaw)는 현재 경로 편집에서 지원하지 않습니다. originYaw=0 지도를 사용해 주세요.')
  }
  return { resolution, originX, originY, width: map.width, height: map.height }
}

/** 좌표 편집 진입 전에 현재 지원 범위를 명시적으로 확인한다. */
export function assertSupportedMapCoordinates(map: MapDetailResponse) {
  numericMetadata(map)
}

/** 지도 이미지 안의 비율 좌표(왼쪽 위가 0,0)를 SLAM map 좌표로 바꾼다. */
export function mapRatiosToWorld(map: MapDetailResponse, point: MapRatios): MapPoint {
  const { resolution, originX, originY, width, height } = numericMetadata(map)
  const xRatio = clamp(point.xRatio, 0, 1)
  const yRatio = clamp(point.yRatio, 0, 1)
  return {
    x: originX + xRatio * width * resolution,
    y: originY + (height - yRatio * height) * resolution,
  }
}

/** SLAM map 좌표를 지도 이미지 비율 좌표(왼쪽 위가 0,0)로 바꾼다. */
export function worldToMapRatios(map: MapDetailResponse, point: MapPoint): MapRatios {
  const { resolution, originX, originY, width, height } = numericMetadata(map)
  return {
    xRatio: (point.x - originX) / resolution / width,
    yRatio: (height - (point.y - originY) / resolution) / height,
  }
}

export function gridRectToWorldBounds(
  map: MapDetailResponse,
  rect: GridRect,
  columns: number,
  rows: number,
): WorldBounds {
  const bottomLeft = mapRatiosToWorld(map, {
    xRatio: rect.x / columns,
    yRatio: (rect.y + rect.h) / rows,
  })
  const topRight = mapRatiosToWorld(map, {
    xRatio: (rect.x + rect.w) / columns,
    yRatio: rect.y / rows,
  })
  return {
    minX: bottomLeft.x,
    minY: bottomLeft.y,
    maxX: topRight.x,
    maxY: topRight.y,
  }
}

/** 서버 구역을 기존 정수 그리드 편집기로 되돌릴 때 원 구역 전체가 보이도록 바깥쪽 셀로 맞춘다. */
export function worldBoundsToGridRect(
  map: MapDetailResponse,
  bounds: WorldBounds,
  columns: number,
  rows: number,
): GridRect {
  const topLeft = worldToMapRatios(map, { x: bounds.minX, y: bounds.maxY })
  const bottomRight = worldToMapRatios(map, { x: bounds.maxX, y: bounds.minY })
  const left = clamp(Math.floor(topLeft.xRatio * columns), 0, columns - 1)
  const top = clamp(Math.floor(topLeft.yRatio * rows), 0, rows - 1)
  const right = clamp(Math.ceil(bottomRight.xRatio * columns), left + 1, columns)
  const bottom = clamp(Math.ceil(bottomRight.yRatio * rows), top + 1, rows)
  return { x: left, y: top, w: right - left, h: bottom - top }
}

export function zoneBounds(zone: ZoneCreateResponse): WorldBounds {
  const bounds = {
    minX: Number(zone.minX),
    minY: Number(zone.minY),
    maxX: Number(zone.maxX),
    maxY: Number(zone.maxY),
  }
  if (
    !Object.values(bounds).every(Number.isFinite) ||
    bounds.minX > bounds.maxX || bounds.minY > bounds.maxY
  ) {
    throw new Error(`구역 '${zone.name}'의 좌표가 올바르지 않습니다.`)
  }
  return bounds
}

export function isWorldPointInMap(map: MapDetailResponse, point: MapPoint) {
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return false
  const ratios = worldToMapRatios(map, point)
  // OccupancyGrid의 유효 셀 범위는 world x/y 상한을 포함하지 않는다.
  // 이미지 좌표에서는 오른쪽(xRatio=1)과 위쪽(yRatio=0)이 그 배타 상한이다.
  return (
    ratios.xRatio >= 0 && ratios.xRatio < 1 &&
    ratios.yRatio > 0 && ratios.yRatio <= 1
  )
}

export function isWorldPointInBounds(point: MapPoint, bounds: WorldBounds) {
  return (
    point.x >= bounds.minX && point.x <= bounds.maxX &&
    point.y >= bounds.minY && point.y <= bounds.maxY
  )
}
