import type { ZoneCreateResponse } from '../../api/contracts'

export type MapCoordinateMetadata = {
  resolution: number | string
  originX: number | string
  originY: number | string
  originYaw: number | string
  width: number
  height: number
}

export type GridRect = { x: number; y: number; w: number; h: number }
export type MapPoint = { x: number; y: number }
export type MapPixel = { x: number; y: number }
export type MapRatios = { xRatio: number; yRatio: number }
export type WorldBounds = { minX: number; minY: number; maxX: number; maxY: number }

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value))

export function numericMapMetadata(map: MapCoordinateMetadata) {
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
  return { resolution, originX, originY, originYaw, width: map.width, height: map.height }
}

/** 좌표 편집 진입 전에 현재 지원 범위를 명시적으로 확인한다. */
export function assertSupportedMapCoordinates(map: MapCoordinateMetadata) {
  numericMapMetadata(map)
}

/** OccupancyGrid 이미지 좌표(왼쪽 위 원점)를 map metadata가 정의한 ROS world 좌표로 바꾼다. */
export function mapPixelToWorld(map: MapCoordinateMetadata, point: MapPixel): MapPoint {
  const { resolution, originX, originY, originYaw, height } = numericMapMetadata(map)
  const localX = point.x * resolution
  const localY = (height - point.y) * resolution
  const cosYaw = Math.cos(originYaw)
  const sinYaw = Math.sin(originYaw)
  return {
    x: originX + cosYaw * localX - sinYaw * localY,
    y: originY + sinYaw * localX + cosYaw * localY,
  }
}

/** ROS world 좌표를 OccupancyGrid 이미지 좌표(왼쪽 위 원점)로 역변환한다. */
export function worldToMapPixel(map: MapCoordinateMetadata, point: MapPoint): MapPixel {
  const { resolution, originX, originY, originYaw, height } = numericMapMetadata(map)
  const dx = point.x - originX
  const dy = point.y - originY
  const cosYaw = Math.cos(originYaw)
  const sinYaw = Math.sin(originYaw)
  const localX = cosYaw * dx + sinYaw * dy
  const localY = -sinYaw * dx + cosYaw * dy
  return {
    x: localX / resolution,
    y: height - localY / resolution,
  }
}

/** 지도 이미지 안의 비율 좌표(왼쪽 위가 0,0)를 SLAM map 좌표로 바꾼다. */
export function mapRatiosToWorld(map: MapCoordinateMetadata, point: MapRatios): MapPoint {
  const { width, height } = numericMapMetadata(map)
  const xRatio = clamp(point.xRatio, 0, 1)
  const yRatio = clamp(point.yRatio, 0, 1)
  return mapPixelToWorld(map, { x: xRatio * width, y: yRatio * height })
}

/** SLAM map 좌표를 지도 이미지 비율 좌표(왼쪽 위가 0,0)로 바꾼다. */
export function worldToMapRatios(map: MapCoordinateMetadata, point: MapPoint): MapRatios {
  const { width, height } = numericMapMetadata(map)
  const pixel = worldToMapPixel(map, point)
  return {
    xRatio: pixel.x / width,
    yRatio: pixel.y / height,
  }
}

export function worldBoundsFromPoints(a: MapPoint, b: MapPoint): WorldBounds {
  return {
    minX: Math.min(a.x, b.x),
    minY: Math.min(a.y, b.y),
    maxX: Math.max(a.x, b.x),
    maxY: Math.max(a.y, b.y),
  }
}

export function worldBoundsOverlap(a: WorldBounds, b: WorldBounds) {
  return a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY
}

export function worldBoundsCorners(bounds: WorldBounds): MapPoint[] {
  return [
    { x: bounds.minX, y: bounds.minY },
    { x: bounds.maxX, y: bounds.minY },
    { x: bounds.maxX, y: bounds.maxY },
    { x: bounds.minX, y: bounds.maxY },
  ]
}

export function gridRectToWorldBounds(
  map: MapCoordinateMetadata,
  rect: GridRect,
  columns: number,
  rows: number,
): WorldBounds {
  const corners = [
    { xRatio: rect.x / columns, yRatio: rect.y / rows },
    { xRatio: (rect.x + rect.w) / columns, yRatio: rect.y / rows },
    { xRatio: (rect.x + rect.w) / columns, yRatio: (rect.y + rect.h) / rows },
    { xRatio: rect.x / columns, yRatio: (rect.y + rect.h) / rows },
  ].map((point) => mapRatiosToWorld(map, point))
  const xs = corners.map((point) => point.x)
  const ys = corners.map((point) => point.y)
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  }
}

/** 서버 구역을 기존 정수 그리드 편집기로 되돌릴 때 원 구역 전체가 보이도록 바깥쪽 셀로 맞춘다. */
export function worldBoundsToGridRect(
  map: MapCoordinateMetadata,
  bounds: WorldBounds,
  columns: number,
  rows: number,
): GridRect {
  const ratios = worldBoundsCorners(bounds).map((point) => worldToMapRatios(map, point))
  const xRatios = ratios.map((point) => point.xRatio)
  const yRatios = ratios.map((point) => point.yRatio)
  const left = clamp(Math.floor(Math.min(...xRatios) * columns), 0, columns - 1)
  const top = clamp(Math.floor(Math.min(...yRatios) * rows), 0, rows - 1)
  const right = clamp(Math.ceil(Math.max(...xRatios) * columns), left + 1, columns)
  const bottom = clamp(Math.ceil(Math.max(...yRatios) * rows), top + 1, rows)
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

export function isWorldPointInMap(map: MapCoordinateMetadata, point: MapPoint) {
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
