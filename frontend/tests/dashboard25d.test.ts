import assert from 'node:assert/strict'
import test from 'node:test'
import type { ComplexMapData } from '../src/types/domain.ts'
import {
  complexMapCoordinateMetadata,
  worldToDashboardGrid,
} from '../src/features/dashboard/mapCoordinateMetadata.ts'
import {
  mapPixelToWorld,
  worldToMapPixel,
} from '../src/features/onboarding/mapCoordinates.ts'
import {
  applyIsometricScreenFit,
  applyViewTransform,
  createIsometricProjection,
  fitIsometricProjection,
  invertIsometricScreenFit,
  invertViewTransform,
  isometricToWorld,
  worldToIsometric,
} from '../src/features/onboarding/mapProjection25d.ts'

const EPSILON = 1e-8

function close(actual: number, expected: number) {
  assert.ok(Math.abs(actual - expected) <= EPSILON, `${actual} != ${expected}`)
}

function map(overrides: Partial<ComplexMapData> = {}): ComplexMapData {
  return {
    cols: 14,
    rows: 7,
    zones: [],
    mapId: 'active-map',
    resolution: 0.05,
    originX: -2.4,
    originY: 1.1,
    originYaw: Math.PI / 6,
    pixelWidth: 200,
    pixelHeight: 120,
    ...overrides,
  }
}

test('Dashboard world position uses active map metadata including originYaw', () => {
  const activeMap = map()
  const metadata = complexMapCoordinateMetadata(activeMap)
  assert.ok(metadata)
  const world = mapPixelToWorld(metadata, { x: 50, y: 30 })
  const grid = worldToDashboardGrid(activeMap, world)
  assert.ok(grid)
  close(grid.x, 3.5)
  close(grid.y, 1.75)
  close(grid.worldX, world.x)
  close(grid.worldY, world.y)
})

test('Robot, waypoint and event world coordinates share one 2.5D projection', () => {
  const metadata = complexMapCoordinateMetadata(map())
  assert.ok(metadata)
  const projection = createIsometricProjection(metadata)
  const world = mapPixelToWorld(metadata, { x: 112.5, y: 44.25 })
  const robotScreen = worldToIsometric(metadata, projection, world)
  const waypointScreen = worldToIsometric(metadata, projection, world)
  const eventScreen = worldToIsometric(metadata, projection, world)
  assert.deepEqual(robotScreen, waypointScreen)
  assert.deepEqual(robotScreen, eventScreen)
  const restored = isometricToWorld(metadata, projection, robotScreen)
  close(restored.x, world.x)
  close(restored.y, world.y)
})

test('a new active map replaces all previous projection constants', () => {
  const first = complexMapCoordinateMetadata(map())
  const second = complexMapCoordinateMetadata(map({
    mapId: 'replacement-map',
    resolution: 0.1,
    originX: 18,
    originY: -7,
    originYaw: -0.4,
    pixelWidth: 80,
    pixelHeight: 60,
  }))
  assert.ok(first)
  assert.ok(second)
  const pixel = { x: 40, y: 20 }
  const firstWorld = mapPixelToWorld(first, pixel)
  const secondWorld = mapPixelToWorld(second, pixel)
  assert.notDeepEqual(firstWorld, secondWorld)
  const restored = worldToMapPixel(second, secondWorld)
  close(restored.x, pixel.x)
  close(restored.y, pixel.y)
})

test('2.5D mode fails closed when complete map metadata is unavailable', () => {
  assert.equal(complexMapCoordinateMetadata(map({ originYaw: Number.NaN })), undefined)
  assert.equal(complexMapCoordinateMetadata(map({ pixelWidth: undefined })), undefined)
})

test('screen fit keeps robot, waypoint, zone and event aligned with the 2D logical map', () => {
  const activeMap = map({ originYaw: -0.43 })
  const metadata = complexMapCoordinateMetadata(activeMap)
  assert.ok(metadata)
  const projection = createIsometricProjection(metadata, { tileX: 1, tileY: 0.58, margin: 8 })
  const fixtures = [
    { kind: 'robot', pixel: { x: 32.25, y: 88.5 } },
    { kind: 'waypoint', pixel: { x: 116.75, y: 41.25 } },
    { kind: 'zone-corner', pixel: { x: 154, y: 72 } },
    { kind: 'event', pixel: { x: 83.5, y: 104.75 } },
  ].map((fixture) => ({
    ...fixture,
    world: mapPixelToWorld(metadata, fixture.pixel),
  }))
  const viewports = [
    { width: 1366, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]
  const view = { zoom: 1.45, panX: 37, panY: -24 }

  for (const viewport of viewports) {
    const fit = fitIsometricProjection(projection, viewport, 0.065)
    const fittedWidthRatio = projection.viewWidth * fit.scale / viewport.width
    assert.ok(
      fittedWidthRatio >= 0.8 && fittedWidthRatio <= 0.9,
      `map width ratio ${fittedWidthRatio} must stay within the visual fit target`,
    )
    for (const fixture of fixtures) {
      const point2d = worldToDashboardGrid(activeMap, fixture.world)
      assert.ok(point2d, `${fixture.kind} must be visible in 2D`)

      const iso = worldToIsometric(metadata, projection, fixture.world)
      const fitted = applyIsometricScreenFit(iso, fit)
      const displayed = applyViewTransform(fitted, view)
      const restoredFitPoint = invertViewTransform(displayed, view)
      const restoredIso = invertIsometricScreenFit(restoredFitPoint, fit)
      const restoredWorld = isometricToWorld(metadata, projection, restoredIso)
      const point25d = worldToDashboardGrid(activeMap, restoredWorld)
      assert.ok(point25d, `${fixture.kind} must be visible in 2.5D`)

      close(point25d.x / activeMap.cols, point2d.x / activeMap.cols)
      close(point25d.y / activeMap.rows, point2d.y / activeMap.rows)
      close(point25d.worldX, point2d.worldX)
      close(point25d.worldY, point2d.worldY)
    }
  }
})
