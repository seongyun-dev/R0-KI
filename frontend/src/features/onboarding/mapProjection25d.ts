import {
  mapPixelToWorld,
  numericMapMetadata,
  worldBoundsCorners,
  worldToMapPixel,
  type MapPixel,
  type MapPoint,
  type MapCoordinateMetadata,
  type WorldBounds,
} from './mapCoordinates.ts'

export type IsometricPoint = { x: number; y: number }
export type IsometricProjection = {
  mapWidth: number
  mapHeight: number
  tileX: number
  tileY: number
  offsetX: number
  offsetY: number
  viewWidth: number
  viewHeight: number
}
export type SvgViewBox = { x: number; y: number; width: number; height: number }
export type ViewTransform = { zoom: number; panX: number; panY: number }
export type ClientRect = { left: number; top: number; width: number; height: number }
export type IsometricScreenFit = {
  scale: number
  translateX: number
  translateY: number
  viewportWidth: number
  viewportHeight: number
}

export const MAP_25D_PROJECTION_OPTIONS = { tileX: 1, tileY: 0.58, margin: 8 } as const
export const MAP_25D_WALL_HEIGHT_PX = 12

export function createIsometricProjection(
  map: MapCoordinateMetadata,
  options: { tileX?: number; tileY?: number; margin?: number } = {},
): IsometricProjection {
  const { width, height } = numericMapMetadata(map)
  const tileX = options.tileX ?? 1
  const tileY = options.tileY ?? 0.5
  const margin = options.margin ?? Math.max(12, Math.min(width, height) * 0.08)
  if (tileX <= 0 || tileY <= 0 || margin < 0) {
    throw new Error('2.5D projection 설정이 올바르지 않습니다.')
  }
  return {
    mapWidth: width,
    mapHeight: height,
    tileX,
    tileY,
    offsetX: height * tileX + margin,
    offsetY: margin,
    viewWidth: (width + height) * tileX + margin * 2,
    viewHeight: (width + height) * tileY + margin * 2,
  }
}

export function mapPixelToIsometric(
  projection: IsometricProjection,
  point: MapPixel,
): IsometricPoint {
  return {
    x: projection.offsetX + (point.x - point.y) * projection.tileX,
    y: projection.offsetY + (point.x + point.y) * projection.tileY,
  }
}

export function isometricToMapPixel(
  projection: IsometricProjection,
  point: IsometricPoint,
): MapPixel {
  const rawX = (point.x - projection.offsetX) / projection.tileX
  const rawY = (point.y - projection.offsetY) / projection.tileY
  const pixelX = (rawX + rawY) / 2
  const pixelY = (rawY - rawX) / 2
  return { x: pixelX, y: pixelY }
}

export function worldToIsometric(
  map: MapCoordinateMetadata,
  projection: IsometricProjection,
  point: MapPoint,
) {
  return mapPixelToIsometric(projection, worldToMapPixel(map, point))
}

export function isometricToWorld(
  map: MapCoordinateMetadata,
  projection: IsometricProjection,
  point: IsometricPoint,
) {
  return mapPixelToWorld(map, isometricToMapPixel(projection, point))
}

export function worldBoundsToIsometricPolygon(
  map: MapCoordinateMetadata,
  projection: IsometricProjection,
  bounds: WorldBounds,
) {
  return worldBoundsCorners(bounds).map((point) => worldToIsometric(map, projection, point))
}

export function applyViewTransform(point: IsometricPoint, view: ViewTransform): IsometricPoint {
  return {
    x: view.panX + point.x * view.zoom,
    y: view.panY + point.y * view.zoom,
  }
}

export function invertViewTransform(point: IsometricPoint, view: ViewTransform): IsometricPoint {
  if (!Number.isFinite(view.zoom) || view.zoom <= 0) throw new Error('zoom은 0보다 커야 합니다.')
  return {
    x: (point.x - view.panX) / view.zoom,
    y: (point.y - view.panY) / view.zoom,
  }
}

/** SVG preserveAspectRatio="xMidYMid meet" 기준 client 좌표를 viewBox 좌표로 복원한다. */
export function clientToSvgPoint(
  client: IsometricPoint,
  rect: ClientRect,
  viewBox: SvgViewBox,
): IsometricPoint {
  if (rect.width <= 0 || rect.height <= 0 || viewBox.width <= 0 || viewBox.height <= 0) {
    throw new Error('SVG 화면 크기가 올바르지 않습니다.')
  }
  const scale = Math.min(rect.width / viewBox.width, rect.height / viewBox.height)
  const renderedWidth = viewBox.width * scale
  const renderedHeight = viewBox.height * scale
  const offsetX = rect.left + (rect.width - renderedWidth) / 2
  const offsetY = rect.top + (rect.height - renderedHeight) / 2
  return {
    x: viewBox.x + (client.x - offsetX) / scale,
    y: viewBox.y + (client.y - offsetY) / scale,
  }
}

/** 테스트 및 pointer delta 계산용 정방향 변환. */
export function svgPointToClient(
  point: IsometricPoint,
  rect: ClientRect,
  viewBox: SvgViewBox,
): IsometricPoint {
  if (rect.width <= 0 || rect.height <= 0 || viewBox.width <= 0 || viewBox.height <= 0) {
    throw new Error('SVG 화면 크기가 올바르지 않습니다.')
  }
  const scale = Math.min(rect.width / viewBox.width, rect.height / viewBox.height)
  const renderedWidth = viewBox.width * scale
  const renderedHeight = viewBox.height * scale
  const offsetX = rect.left + (rect.width - renderedWidth) / 2
  const offsetY = rect.top + (rect.height - renderedHeight) / 2
  return {
    x: offsetX + (point.x - viewBox.x) * scale,
    y: offsetY + (point.y - viewBox.y) * scale,
  }
}

export function pointsAttribute(points: IsometricPoint[]) {
  return points.map((point) => `${point.x},${point.y}`).join(' ')
}

/** Fit projection coordinates into a viewport without changing map/world geometry. */
export function fitIsometricProjection(
  projection: IsometricProjection,
  viewport: { width: number; height: number },
  paddingRatio = 0.07,
): IsometricScreenFit {
  if (
    !Number.isFinite(viewport.width) || viewport.width <= 0 ||
    !Number.isFinite(viewport.height) || viewport.height <= 0 ||
    !Number.isFinite(paddingRatio) || paddingRatio < 0 || paddingRatio >= 0.5
  ) {
    throw new Error('2.5D 화면 fit 설정이 올바르지 않습니다.')
  }
  const availableWidth = viewport.width * (1 - paddingRatio * 2)
  const availableHeight = viewport.height * (1 - paddingRatio * 2)
  const scale = Math.min(
    availableWidth / projection.viewWidth,
    availableHeight / projection.viewHeight,
  )
  return {
    scale,
    translateX: (viewport.width - projection.viewWidth * scale) / 2,
    translateY: (viewport.height - projection.viewHeight * scale) / 2,
    viewportWidth: viewport.width,
    viewportHeight: viewport.height,
  }
}

export function applyIsometricScreenFit(
  point: IsometricPoint,
  fit: IsometricScreenFit,
): IsometricPoint {
  return {
    x: fit.translateX + point.x * fit.scale,
    y: fit.translateY + point.y * fit.scale,
  }
}

export function invertIsometricScreenFit(
  point: IsometricPoint,
  fit: IsometricScreenFit,
): IsometricPoint {
  if (!Number.isFinite(fit.scale) || fit.scale <= 0) {
    throw new Error('2.5D 화면 fit scale은 0보다 커야 합니다.')
  }
  return {
    x: (point.x - fit.translateX) / fit.scale,
    y: (point.y - fit.translateY) / fit.scale,
  }
}
