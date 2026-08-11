import assert from 'node:assert/strict'
import test from 'node:test'
import type { MapDetailResponse } from '../src/api/contracts.ts'
import {
  gridRectToWorldBounds,
  mapPixelToWorld,
  mapRatiosToWorld,
  worldBoundsFromPoints,
  worldBoundsCorners,
  worldBoundsToGridRect,
  worldToMapPixel,
} from '../src/features/onboarding/mapCoordinates.ts'
import {
  applyViewTransform,
  clientToSvgPoint,
  createIsometricProjection,
  invertViewTransform,
  isometricToWorld,
  svgPointToClient,
  worldBoundsToIsometricPolygon,
  worldToIsometric,
  type ClientRect,
  type ViewTransform,
} from '../src/features/onboarding/mapProjection25d.ts'

const EPSILON = 1e-8

function close(actual: number, expected: number, message?: string) {
  assert.ok(Math.abs(actual - expected) <= EPSILON, message ?? `${actual} != ${expected}`)
}

function closePoint(actual: { x: number; y: number }, expected: { x: number; y: number }) {
  close(actual.x, expected.x, 'x coordinate differs')
  close(actual.y, expected.y, 'y coordinate differs')
}

function map(overrides: Partial<MapDetailResponse> = {}): MapDetailResponse {
  return {
    mapId: 71,
    mapName: 'coordinate-test',
    mapUrl: '/maps/71.png',
    resolution: 0.05,
    originX: -3.2,
    originY: 1.4,
    originYaw: 0,
    width: 240,
    height: 160,
    mapVersion: 4,
    ...overrides,
  }
}

function roundTripThroughScreen(
  metadata: MapDetailResponse,
  world: { x: number; y: number },
  view: ViewTransform,
  rect: ClientRect,
) {
  const projection = createIsometricProjection(metadata)
  const viewBox = { x: 0, y: 0, width: projection.viewWidth, height: projection.viewHeight }
  const iso = worldToIsometric(metadata, projection, world)
  const screen = svgPointToClient(applyViewTransform(iso, view), rect, viewBox)
  const svg = clientToSvgPoint(screen, rect, viewBox)
  return isometricToWorld(metadata, projection, invertViewTransform(svg, view))
}

test('originYaw=0 map pixel and world coordinates round-trip', () => {
  const metadata = map()
  const pixel = { x: 37.25, y: 118.75 }
  closePoint(worldToMapPixel(metadata, mapPixelToWorld(metadata, pixel)), pixel)
})
test('non-zero originYaw is supported by forward and inverse transforms', () => {
  const metadata = map({ originX: 4.5, originY: -2.1, originYaw: Math.PI / 3 })
  const pixel = { x: 92.4, y: 41.8 }
  closePoint(worldToMapPixel(metadata, mapPixelToWorld(metadata, pixel)), pixel)
})

test('world to 2.5D screen to world round-trip survives zoom and pan', () => {
  const metadata = map({ originYaw: -0.37 })
  const world = mapPixelToWorld(metadata, { x: 152.5, y: 63.75 })
  const result = roundTripThroughScreen(
    metadata,
    world,
    { zoom: 2.35, panX: -83.4, panY: 46.2 },
    { left: 120, top: 48, width: 960, height: 520 },
  )
  closePoint(result, world)
})

test('2.5D Zone polygon boundaries restore the same world bounds', () => {
  const metadata = map({ originYaw: 0.42 })
  const projection = createIsometricProjection(metadata)
  const bounds = { minX: -0.8, minY: 3.1, maxX: 2.2, maxY: 5.6 }
  const restored = worldBoundsToIsometricPolygon(metadata, projection, bounds)
    .map((point) => isometricToWorld(metadata, projection, point))
  worldBoundsCorners(bounds).forEach((point, index) => closePoint(restored[index], point))
})

test('browser resize does not change the selected world point', () => {
  const metadata = map({ originYaw: 0.18 })
  const world = mapPixelToWorld(metadata, { x: 108, y: 74 })
  const view = { zoom: 1.6, panX: 32, panY: -18 }
  const wide = roundTripThroughScreen(metadata, world, view, {
    left: 0,
    top: 0,
    width: 1100,
    height: 620,
  })
  const narrow = roundTripThroughScreen(metadata, world, view, {
    left: 15,
    top: 30,
    width: 430,
    height: 680,
  })
  closePoint(wide, world)
  closePoint(narrow, world)
})

test('2D and 2.5D selection recover the same physical point', () => {
  const metadata = map({ originYaw: -0.25 })
  const ratios = { xRatio: 0.64, yRatio: 0.31 }
  const from2d = mapRatiosToWorld(metadata, ratios)
  const from25d = roundTripThroughScreen(
    metadata,
    from2d,
    { zoom: 1, panX: 0, panY: 0 },
    { left: 5, top: 9, width: 800, height: 400 },
  )
  closePoint(from25d, from2d)
})

test('2D and 2.5D preserve the same raw map top/bottom orientation', () => {
  const metadata = map()
  const projection = createIsometricProjection(metadata)
  const top = worldToIsometric(metadata, projection, mapRatiosToWorld(metadata, { xRatio: 0.5, yRatio: 0.2 }))
  const bottom = worldToIsometric(metadata, projection, mapRatiosToWorld(metadata, { xRatio: 0.5, yRatio: 0.8 }))
  assert.ok(top.y < bottom.y, '2.5D must preserve the 2D map top-to-bottom display orientation')
})

test('2D and 2.5D drag endpoints serialize identical Zone world bounds', () => {
  const metadata = map({ originYaw: 0.31 })
  const start2d = mapRatiosToWorld(metadata, { xRatio: 0.18, yRatio: 0.27 })
  const end2d = mapRatiosToWorld(metadata, { xRatio: 0.71, yRatio: 0.76 })
  const rect = { left: 12, top: 24, width: 920, height: 510 }
  const start25d = roundTripThroughScreen(metadata, start2d, { zoom: 1.4, panX: 17, panY: -9 }, rect)
  const end25d = roundTripThroughScreen(metadata, end2d, { zoom: 1.4, panX: 17, panY: -9 }, rect)
  const bounds2d = worldBoundsFromPoints(start2d, end2d)
  const bounds25d = worldBoundsFromPoints(start25d, end25d)
  close(bounds25d.minX, bounds2d.minX)
  close(bounds25d.minY, bounds2d.minY)
  close(bounds25d.maxX, bounds2d.maxX)
  close(bounds25d.maxY, bounds2d.maxY)
})

test('grid fallback derives display cells from world bounds', () => {
  const metadata = map()
  const rect = { x: 2, y: 1, w: 4, h: 3 }
  const bounds = gridRectToWorldBounds(metadata, rect, 14, 7)
  assert.deepEqual(worldBoundsToGridRect(metadata, bounds, 14, 7), rect)
})

test('new map metadata is used instead of previous map constants', () => {
  const first = map()
  const second = map({
    mapId: 72,
    mapVersion: 1,
    resolution: 0.1,
    originX: 24,
    originY: -11,
    originYaw: 0.7,
    width: 90,
    height: 60,
  })
  const pixel = { x: 45, y: 30 }
  const firstWorld = mapPixelToWorld(first, pixel)
  const secondWorld = mapPixelToWorld(second, pixel)
  assert.notDeepEqual(firstWorld, secondWorld)
  closePoint(worldToMapPixel(second, secondWorld), pixel)
})
