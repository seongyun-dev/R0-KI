export type DisplayMaskCleanupOptions = {
  maxNoiseComponentPx?: number
}

const NEIGHBORS = [
  [-1, -1], [0, -1], [1, -1],
  [-1, 0],           [1, 0],
  [-1, 1],  [0, 1],  [1, 1],
] as const

function validateMask(mask: Uint8Array, width: number, height: number) {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0) {
    throw new Error('display mask 크기가 올바르지 않습니다.')
  }
  if (mask.length !== width * height) {
    throw new Error('display mask 데이터 길이가 올바르지 않습니다.')
  }
}

/**
 * Produce a display-only occupied mask. The source array is never mutated.
 *
 * Only one- or two-pixel disconnected specks are removed. Connected geometry,
 * including rough edges, gaps and narrow wall segments, stays byte-for-byte raw.
 */
export function cleanupDisplayOccupiedMask(
  source: Uint8Array,
  width: number,
  height: number,
  options: DisplayMaskCleanupOptions = {},
) {
  validateMask(source, width, height)
  const maxNoiseComponentPx = Math.max(0, Math.min(2, options.maxNoiseComponentPx ?? 2))
  const cleaned = source.slice()
  const visited = new Uint8Array(source.length)
  const queue = new Int32Array(source.length)

  for (let start = 0; start < source.length; start += 1) {
    if (!source[start] || visited[start]) continue
    let head = 0
    let tail = 0
    queue[tail++] = start
    visited[start] = 1
    const component: number[] = []

    while (head < tail) {
      const index = queue[head++]
      component.push(index)
      const x = index % width
      const y = Math.floor(index / width)
      for (const [dx, dy] of NEIGHBORS) {
        const nx = x + dx
        const ny = y + dy
        if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue
        const neighbor = ny * width + nx
        if (!source[neighbor] || visited[neighbor]) continue
        visited[neighbor] = 1
        queue[tail++] = neighbor
      }
    }

    if (component.length <= maxNoiseComponentPx) {
      for (const index of component) cleaned[index] = 0
    }
  }

  return cleaned
}

export function rgbaToOccupiedMask(
  rgba: Uint8ClampedArray,
  width: number,
  height: number,
  occupiedLuminanceThreshold = 96,
) {
  if (rgba.length !== width * height * 4) throw new Error('RGBA map 데이터 길이가 올바르지 않습니다.')
  const mask = new Uint8Array(width * height)
  for (let index = 0; index < mask.length; index += 1) {
    const offset = index * 4
    if (rgba[offset + 3] === 0) continue
    const luminance = rgba[offset] * 0.2126 + rgba[offset + 1] * 0.7152 + rgba[offset + 2] * 0.0722
    mask[index] = luminance <= occupiedLuminanceThreshold ? 1 : 0
  }
  return mask
}

/**
 * Return the observed part of a trinary occupancy map for display-only floors.
 *
 * ROS map previews use dark pixels for occupied space, near-white pixels for
 * free space and mid gray (normally 205) for unknown space. Keeping occupied
 * and free pixels while excluding unknown pixels gives the real mapped floor
 * silhouette without reviving the large rectangular/diamond outer slab.
 */
export function rgbaToObservedMask(
  rgba: Uint8ClampedArray,
  width: number,
  height: number,
  unknownLuminanceMin = 176,
  unknownLuminanceMax = 232,
) {
  if (rgba.length !== width * height * 4) throw new Error('RGBA map 데이터 길이가 올바르지 않습니다.')
  if (
    !Number.isFinite(unknownLuminanceMin)
    || !Number.isFinite(unknownLuminanceMax)
    || unknownLuminanceMin < 0
    || unknownLuminanceMax > 255
    || unknownLuminanceMin >= unknownLuminanceMax
  ) {
    throw new Error('unknown luminance 범위가 올바르지 않습니다.')
  }
  const mask = new Uint8Array(width * height)
  for (let index = 0; index < mask.length; index += 1) {
    const offset = index * 4
    if (rgba[offset + 3] === 0) continue
    const luminance = rgba[offset] * 0.2126 + rgba[offset + 1] * 0.7152 + rgba[offset + 2] * 0.0722
    mask[index] = luminance < unknownLuminanceMin || luminance > unknownLuminanceMax ? 1 : 0
  }
  return mask
}

export function occupiedMaskToImageData(mask: Uint8Array, width: number, height: number) {
  validateMask(mask, width, height)
  const rgba = new Uint8ClampedArray(width * height * 4)
  for (let index = 0; index < mask.length; index += 1) {
    const value = mask[index] ? 0 : 255
    const offset = index * 4
    rgba[offset] = value
    rgba[offset + 1] = value
    rgba[offset + 2] = value
    rgba[offset + 3] = 255
  }
  return new ImageData(rgba, width, height)
}

export function observedMaskToImageData(mask: Uint8Array, width: number, height: number) {
  validateMask(mask, width, height)
  const rgba = new Uint8ClampedArray(width * height * 4)
  for (let index = 0; index < mask.length; index += 1) {
    if (!mask[index]) continue
    const offset = index * 4
    rgba[offset] = 255
    rgba[offset + 1] = 255
    rgba[offset + 2] = 255
    rgba[offset + 3] = 255
  }
  return new ImageData(rgba, width, height)
}
