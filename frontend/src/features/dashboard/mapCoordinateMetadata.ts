import type { ComplexMapData } from '../../types/domain'
import {
  numericMapMetadata,
  worldToMapRatios,
  type MapCoordinateMetadata,
  type MapPoint,
} from '../onboarding/mapCoordinates.ts'

export function complexMapCoordinateMetadata(
  map: ComplexMapData,
): MapCoordinateMetadata | undefined {
  if (
    map.resolution == null ||
    map.originX == null ||
    map.originY == null ||
    map.pixelWidth == null ||
    map.pixelHeight == null
  ) return undefined

  const metadata: MapCoordinateMetadata = {
    resolution: map.resolution,
    originX: map.originX,
    originY: map.originY,
    originYaw: map.originYaw ?? 0,
    width: map.pixelWidth,
    height: map.pixelHeight,
  }
  try {
    numericMapMetadata(metadata)
    return metadata
  } catch {
    return undefined
  }
}

export function worldToDashboardGrid(
  map: ComplexMapData,
  point: MapPoint,
) {
  const metadata = complexMapCoordinateMetadata(map)
  if (!metadata || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return undefined
  const ratios = worldToMapRatios(metadata, point)
  const clamp = (value: number, max: number) => Math.max(0, Math.min(max, value))
  return {
    x: clamp(ratios.xRatio * map.cols, map.cols),
    y: clamp(ratios.yRatio * map.rows, map.rows),
    worldX: point.x,
    worldY: point.y,
  }
}
