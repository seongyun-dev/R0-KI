import assert from 'node:assert/strict'
import test from 'node:test'
import {
  cleanupDisplayOccupiedMask,
  rgbaToObservedMask,
  rgbaToOccupiedMask,
} from '../src/features/dashboard/displayGeometry25d.ts'

function mask(width: number, height: number, occupied: Array<[number, number]>) {
  const result = new Uint8Array(width * height)
  for (const [x, y] of occupied) result[y * width + x] = 1
  return result
}

function majorComponents(source: Uint8Array, width: number, height: number) {
  const seen = new Uint8Array(source.length)
  const components: Array<{ size: number; minX: number; minY: number; maxX: number; maxY: number }> = []
  for (let start = 0; start < source.length; start += 1) {
    if (!source[start] || seen[start]) continue
    const queue = [start]
    seen[start] = 1
    const component = { size: 0, minX: width, minY: height, maxX: 0, maxY: 0 }
    while (queue.length) {
      const index = queue.pop()!
      const x = index % width
      const y = Math.floor(index / width)
      component.size += 1
      component.minX = Math.min(component.minX, x)
      component.minY = Math.min(component.minY, y)
      component.maxX = Math.max(component.maxX, x)
      component.maxY = Math.max(component.maxY, y)
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          const nx = x + dx
          const ny = y + dy
          const next = ny * width + nx
          if ((dx || dy) && nx >= 0 && nx < width && ny >= 0 && ny < height && source[next] && !seen[next]) {
            seen[next] = 1
            queue.push(next)
          }
        }
      }
    }
    if (component.size >= 4) components.push(component)
  }
  return components
}

test('display cleanup removes only one and two pixel isolated components', () => {
  const width = 8
  const source = mask(width, 7, [
    [1, 1],
    [5, 1], [5, 2],
    [2, 4], [3, 4], [2, 5], [3, 5],
  ])
  const cleaned = cleanupDisplayOccupiedMask(source, width, 7)
  assert.equal(cleaned[1 * width + 1], 0)
  assert.equal(cleaned[1 * width + 5], 0)
  assert.equal(cleaned[2 * width + 5], 0)
  assert.equal(cleaned[4 * width + 2], 1)
  assert.equal(cleaned[5 * width + 3], 1)
  assert.equal(source[1 * width + 1], 1, 'source mask must remain unchanged')
})

test('display cleanup preserves real wall segments and map dimensions', () => {
  const source = mask(7, 5, [[2, 2], [3, 2], [4, 2]])
  const cleaned = cleanupDisplayOccupiedMask(source, 7, 5)
  assert.equal(cleaned.length, source.length)
  assert.deepEqual([...cleaned], [...source])
})

test('display cleanup fills only a fully surrounded one-pixel pinhole', () => {
  const occupied: Array<[number, number]> = []
  for (let y = 1; y <= 3; y += 1) {
    for (let x = 1; x <= 3; x += 1) {
      if (x !== 2 || y !== 2) occupied.push([x, y])
    }
  }
  const cleaned = cleanupDisplayOccupiedMask(mask(5, 5, occupied), 5, 5)
  assert.equal(cleaned[2 * 5 + 2], 1)
})

test('display cleanup does not close a corridor or doorway gap', () => {
  const source = mask(7, 5, [[1, 2], [2, 2], [4, 2], [5, 2]])
  const cleaned = cleanupDisplayOccupiedMask(source, 7, 5)
  assert.equal(cleaned[2 * 7 + 3], 0)
})

test('strong display cleanup preserves major components, bounds and representative opening', () => {
  const width = 14
  const height = 9
  const occupied: Array<[number, number]> = []
  for (let y = 2; y <= 6; y += 1) {
    for (let x = 1; x <= 4; x += 1) occupied.push([x, y])
    for (let x = 9; x <= 12; x += 1) occupied.push([x, y])
  }
  occupied.push([6, 1], [7, 1], [7, 2])
  const source = mask(width, height, occupied)
  const cleaned = cleanupDisplayOccupiedMask(source, width, height, {
    maxNoiseComponentPx: 4,
    spurPasses: 3,
    axisStraighteningPasses: 2,
  })
  assert.deepEqual(majorComponents(cleaned, width, height), majorComponents(source, width, height).slice(0, 2))
  assert.equal(cleaned[4 * width + 7], 0, 'the opening between major components must remain open')
})

test('axis straightening removes an isolated bump and fills a one-pixel edge notch', () => {
  const width = 9
  const occupied: Array<[number, number]> = []
  for (let y = 3; y <= 5; y += 1) {
    for (let x = 1; x <= 7; x += 1) {
      if (x !== 4 || y !== 3) occupied.push([x, y])
    }
  }
  occupied.push([2, 2])
  const cleaned = cleanupDisplayOccupiedMask(mask(width, 8, occupied), width, 8, {
    axisStraighteningPasses: 1,
  })
  assert.equal(cleaned[2 * width + 2], 0)
  assert.equal(cleaned[3 * width + 4], 1)
})

test('map grayscale conversion keeps unknown and free pixels out of occupied geometry', () => {
  const rgba = new Uint8ClampedArray([
    0, 0, 0, 255,
    205, 205, 205, 255,
    254, 254, 254, 255,
  ])
  assert.deepEqual([...rgbaToOccupiedMask(rgba, 3, 1)], [1, 0, 0])
})

test('observed floor keeps occupied and free space but removes the unknown outer slab', () => {
  const rgba = new Uint8ClampedArray([
    205, 205, 205, 255,
    0, 0, 0, 255,
    254, 254, 254, 255,
    205, 205, 205, 255,
    205, 205, 205, 255,
  ])
  assert.deepEqual([...rgbaToObservedMask(rgba, 5, 1)], [0, 1, 1, 0, 0])
})

test('observed floor conversion is display-only and does not mutate source pixels', () => {
  const rgba = new Uint8ClampedArray([
    0, 0, 0, 255,
    205, 205, 205, 255,
    254, 254, 254, 255,
  ])
  const before = rgba.slice()
  rgbaToObservedMask(rgba, 3, 1)
  assert.deepEqual(rgba, before)
})
