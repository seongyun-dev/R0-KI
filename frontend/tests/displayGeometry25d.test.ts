import assert from 'node:assert/strict'
import test from 'node:test'
import {
  cleanupDisplayOccupiedMask,
  rgbaToOccupiedMask,
} from '../src/features/dashboard/displayGeometry25d.ts'

function mask(width: number, height: number, occupied: Array<[number, number]>) {
  const result = new Uint8Array(width * height)
  for (const [x, y] of occupied) result[y * width + x] = 1
  return result
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

test('map grayscale conversion keeps unknown and free pixels out of occupied geometry', () => {
  const rgba = new Uint8ClampedArray([
    0, 0, 0, 255,
    205, 205, 205, 255,
    254, 254, 254, 255,
  ])
  assert.deepEqual([...rgbaToOccupiedMask(rgba, 3, 1)], [1, 0, 0])
})
